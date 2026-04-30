"""
PDF Service - Manages PDF processing and text extraction using tool-based approach.

Educational Note: This service uses a TOOL-BASED extraction approach where:
- Multiple PDF pages are sent to the model in a single API call (batch)
- Claude sees all pages in the batch for context awareness
- Claude uses the submit_page_extraction tool to return per-page extractions
- This solves the "page boundary" problem (headings on page 1, content on page 2)

Batching Strategy:
- PDFs ≤ 5 pages: Single API call with all pages
- PDFs > 5 pages: Split into batches of 5, process batches in parallel

Why Tools?
- Sending multiple pages and getting a single response loses page boundaries
- Tools let Claude return structured per-page data while having full context
- We force tool use with tool_choice={"type": "any"}

Parallel Processing:
- Uses ThreadPoolExecutor for concurrent batch processing
- Number of workers determined by Anthropic tier setting
- Rate limiting prevents hitting API limits
"""
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.providers.supabase import storage_service
from app.config.tool import tool_loader
from app.config.prompt import render_prompt
from app.config.provider import get_generation_config
from app.sources.extract.batching import create_batches, DEFAULT_BATCH_SIZE
from app.sources.extract.media import pdf_page_part
from app.sources.pdf.ops import get_page_count, get_all_page_bytes
from app.sources.extract.rate import RateLimiter
from app.sources.text import build_processed_output
from app.sources.tokens import count_tokens
from app.background.tasks import task_service
from app.agents.runtime import (
    RunLimits,
    RunMessage,
    RunRequest,
    TextPart,
    ToolChoice,
    bind_local_tools,
    echo_input,
    run_with_provider,
    tool_result_payloads,
)

# Note: Processed output is uploaded to Supabase Storage, not saved locally

logger = logging.getLogger(__name__)


class CancelledException(Exception):
    """Raised when processing is cancelled by user."""
    pass


class PDFService:
    """
    Service class for managing PDF text extraction using tool-based approach.

    Educational Note: This service orchestrates PDF processing:
    1. Splits PDF into batches of pages (max 5 per batch)
    2. Sends each batch to the model API with all pages visible
    3. Claude uses submit_page_extraction tool for each page (with context!)
    4. Collects results, writes to file in page order
    5. For large PDFs, processes batches in parallel
    """

    def __init__(self):
        """Initialize the PDF service."""
        self._tool_definition = None

    def _load_tool_definition(self) -> Dict[str, Any]:
        """
        Load the PDF extraction tool definition.

        Educational Note: The tool definition tells Claude:
        - What the tool does (extract text for a page)
        - What parameters it accepts (page_number, extracted_text, etc.)
        - That it should be called once per page
        """
        if self._tool_definition is None:
            self._tool_definition = tool_loader.load_tool_spec("pdf_tools", "pdf_extraction")
        return self._tool_definition

    def _extract_batch_with_tools(
        self,
        batch: List[Tuple[int, bytes]],
        total_pages: int,
        pdf_name: str,
        tool_def: Dict[str, Any],
        rate_limiter: RateLimiter,
        project_id: str,
        max_retries: int = 3
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Extract text from a batch of PDF pages using tool-based approach.

        Educational Note: This is the core of the new extraction approach:
        1. Build a message with ALL pages in the batch as document blocks
        2. Each document has a title like "filename.pdf - Page 7" for identification
        3. Claude can see all pages → understands cross-page context
        4. Force tool use with tool_choice={"type": "tool", "name": "..."}
        5. Claude calls submit_page_extraction once per page
        6. We parse validated tool results to get per-page extracted text

        Args:
            batch: List of (page_number, page_bytes) tuples
            total_pages: Total pages in the entire PDF (for context)
            pdf_name: Original PDF filename (e.g., "8page.pdf") for document titles
            tool_def: Tool definition for submit_page_extraction
            rate_limiter: RateLimiter instance for API rate limiting
            project_id: Project ID for cost tracking
            max_retries: Maximum retry attempts for failed requests

        Returns:
            Tuple of (first_page_in_batch, results_dict)
        """
        batch_start_page = batch[0][0]
        batch_page_numbers = [p[0] for p in batch]

        content_parts = []
        for page_num, page_bytes in batch:
            content_parts.append(
                pdf_page_part(filename=pdf_name, page_number=page_num, data=page_bytes)
            )

        # Build user message describing what to extract
        # IMPORTANT: Explicitly list the page numbers so Claude uses correct numbering
        if len(batch) == 1:
            extraction_desc = f"page {batch[0][0]}"
            page_list = str(batch[0][0])
        else:
            extraction_desc = f"pages {batch[0][0]} to {batch[-1][0]}"
            page_list = ", ".join(str(p) for p in batch_page_numbers)

        prompt = render_prompt(
            "pdf_extraction",
            {
                "total_pages": total_pages,
                "extraction_description": extraction_desc,
                "expected_tool_calls": len(batch),
                "page_numbers": page_list,
            },
            project_id=project_id,
        )

        content_parts.append(TextPart(text=prompt.user_message or ""))
        messages = [RunMessage(role="user", content=content_parts)]
        tools = bind_local_tools([tool_def], {tool_def.name: echo_input})

        # Retry loop with rate limiting
        last_error = None
        for attempt in range(max_retries):
            try:
                # Apply rate limiting before each API call
                rate_limiter.wait_if_needed()

                result = run_with_provider(
                    RunRequest(
                        provider=prompt.provider,
                        model=prompt.model,
                        purpose="pdf_extraction",
                        messages=messages,
                        system_prompt=prompt.system_prompt,
                        tools=tools,
                        tool_choice=ToolChoice(type="tool", name="submit_page_extraction"),
                        limits=RunLimits(
                            max_tool_turns=1,
                            max_output_tokens=prompt.max_tokens,
                            temperature=prompt.temperature,
                        ),
                        project_id=project_id,
                    )
                )

                # Parse validated runtime tool results from the shared runner.
                page_results = self._parse_tool_results(result, batch_page_numbers)

                return (batch_start_page, {
                    "success": True,
                    "page_results": page_results,
                    "token_usage": result.usage.model_dump(mode="json"),
                    "model": result.model
                })

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Check if it's a rate limit error (429)
                if "rate" in error_str or "429" in error_str or "overloaded" in error_str:
                    wait_time = (attempt + 1) * 30
                    logger.warning("Batch page %d: rate limit hit, waiting %ds (attempt %d/%d)",
                                   batch_start_page, wait_time, attempt + 1, max_retries)
                    time.sleep(wait_time)
                elif attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2
                    logger.warning("Batch page %d: error, retrying in %ds (attempt %d/%d)",
                                   batch_start_page, wait_time, attempt + 1, max_retries)
                    time.sleep(wait_time)

        # All retries exhausted
        return (batch_start_page, {
            "success": False,
            "error": str(last_error),
            "failed_pages": batch_page_numbers
        })

    def _parse_tool_results(
        self,
        response: Any,
        expected_pages: List[int]
    ) -> Dict[int, Dict[str, Any]]:
        """
        Parse PDF extraction tool results from the runtime response.

        Educational Note: Uses runtime-validated tool results, then processes the
        PDF-specific fields (page_number, extracted_text). Each extraction is
        self-contained with context included.

        Args:
            response: Runtime result from the provider adapter
            expected_pages: List of page numbers we expected extractions for

        Returns:
            Dict mapping page_number -> extraction result
        """
        page_results = {}

        # Process PDF-specific fields from validated runtime tool results.
        for tool_input in tool_result_payloads(response, "submit_page_extraction", dict):
            page_num = tool_input.get("page_number")
            extracted_text = tool_input.get("extracted_text", "")

            if page_num is not None:
                page_results[page_num] = {
                    "text": extracted_text
                }

        # Check for missing pages (Claude didn't call tool for some pages)
        missing_pages = set(expected_pages) - set(page_results.keys())
        if missing_pages:
            logger.warning("Missing extractions for pages: %s", sorted(missing_pages))
            # Mark missing pages as errors so the whole extraction fails
            for page_num in missing_pages:
                page_results[page_num] = {
                    "text": "[EXTRACTION FAILED - No tool call received]",
                    "error": "No tool call received for this page"
                }

        return page_results

    def extract_text_from_pdf(
        self,
        project_id: str,
        source_id: str,
        pdf_path: Path
    ) -> Dict[str, Any]:
        """
        Extract text from a PDF file using BATCHED TOOL-BASED processing.

        Educational Note: This method implements the new extraction approach:
        1. Gets total page count and tier configuration
        2. Extracts page bytes for all pages
        3. Splits into batches (max 5 pages per batch)
        4. For each batch: sends all pages, Claude uses tools for per-page extraction
        5. For large PDFs: processes batches in parallel
        6. Collects all results, writes to file in page order

        Benefits over page-by-page:
        - Context awareness: Claude sees surrounding pages
        - Better handling of content spanning page boundaries
        - Fewer API calls (5 pages per call vs 1)

        Args:
            project_id: The project UUID
            source_id: The source UUID
            pdf_path: Path to the PDF file

        Returns:
            Dict with extraction results
        """
        logger.info("Starting PDF extraction for source %s", source_id[:8])

        try:
            # Step 1: Load configurations using centralized loaders
            tool_def = self._load_tool_definition()
            prompt = render_prompt(
                "pdf_extraction",
                {
                    "total_pages": 1,
                    "extraction_description": "configuration probe",
                    "expected_tool_calls": 1,
                    "page_numbers": "1",
                },
                project_id=project_id,
            )
            generation_config = get_generation_config(
                prompt.provider,
                project_id=project_id,
            )
            max_workers = generation_config["max_workers"]
            # For batched approach, rate limit is per batch (API call), not per page
            # Divide pages_per_minute by batch size to get batches_per_minute
            requests_per_minute = generation_config["requests_per_minute"]
            batches_per_minute = max(1, requests_per_minute // DEFAULT_BATCH_SIZE)

            # Create rate limiter for this extraction session
            rate_limiter = RateLimiter(batches_per_minute)

            logger.info(
                "PDF config: provider=%s model=%s workers=%d ~%d batches/min",
                prompt.provider,
                prompt.model,
                max_workers,
                batches_per_minute,
            )

            # Step 2: Get page count and extract all page bytes
            total_pages = get_page_count(pdf_path)
            logger.info("PDF has %d pages", total_pages)

            page_bytes_list = get_all_page_bytes(pdf_path)

            # Step 3: Create batches using utility
            batches = create_batches(page_bytes_list, DEFAULT_BATCH_SIZE)
            total_batches = len(batches)

            # Step 4: Process batches
            all_page_results: Dict[int, Dict[str, Any]] = {}
            total_input_tokens = 0
            total_output_tokens = 0
            batches_completed = 0

            # Get PDF filename for document titles
            pdf_name = pdf_path.name

            if total_batches == 1:
                # Single batch - no need for parallel processing
                _, batch_result = self._extract_batch_with_tools(
                    batches[0],
                    total_pages,
                    pdf_name,
                    tool_def,
                    rate_limiter,
                    project_id
                )

                if not batch_result.get("success"):
                    raise Exception(batch_result.get("error", "Batch extraction failed"))

                all_page_results.update(batch_result.get("page_results", {}))
                total_input_tokens += batch_result.get("token_usage", {}).get("input_tokens", 0)
                total_output_tokens += batch_result.get("token_usage", {}).get("output_tokens", 0)

            else:
                # Multiple batches - process in parallel

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_batch = {
                        executor.submit(
                            self._extract_batch_with_tools,
                            batch,
                            total_pages,
                            pdf_name,
                            tool_def,
                            rate_limiter,
                            project_id
                        ): batch[0][0]  # Track by first page number
                        for batch in batches
                    }

                    for future in as_completed(future_to_batch):
                        # Check for cancellation
                        if task_service.is_target_cancelled(
                            source_id,
                            owner_project_id=project_id,
                        ):
                            for f in future_to_batch:
                                f.cancel()
                            raise CancelledException("Processing cancelled by user")

                        batch_start, batch_result = future.result()
                        batches_completed += 1

                        if batch_result.get("success"):
                            all_page_results.update(batch_result.get("page_results", {}))
                            total_input_tokens += batch_result.get("token_usage", {}).get("input_tokens", 0)
                            total_output_tokens += batch_result.get("token_usage", {}).get("output_tokens", 0)
                        else:
                            failed_pages = batch_result.get("failed_pages", [])
                            error_msg = batch_result.get("error", "Unknown error")
                            logger.error("Batch starting at page %d failed: %s", batch_start, error_msg)
                            # Mark failed pages
                            for page_num in failed_pages:
                                all_page_results[page_num] = {
                                    "text": f"[EXTRACTION FAILED: {error_msg}]",
                                    "error": error_msg
                                }

            # Step 6: Check for failures
            failed_pages = [
                page_num for page_num, result in all_page_results.items()
                if result.get("error")
            ]

            if failed_pages:
                # Don't save partial results - let user retry
                error_message = f"Failed to extract {len(failed_pages)} page(s): {sorted(failed_pages)[:5]}"
                if len(failed_pages) > 5:
                    error_message += f" (and {len(failed_pages) - 5} more)"

                logger.error("Extraction failed: %s", error_message)

                return {
                    "success": False,
                    "status": "error",
                    "error": error_message,
                    "total_pages": total_pages,
                    "failed_pages": sorted(failed_pages)
                }

            # Step 7: Build pages list and write using centralized output format

            # Collect pages in order
            pages = []
            total_characters = 0
            for page_num in sorted(all_page_results.keys()):
                result = all_page_results[page_num]
                extracted_text = result.get("text", "")
                pages.append(extracted_text)
                total_characters += len(extracted_text)

            # Calculate token count for metadata
            full_text = "\n".join(pages)
            token_count = count_tokens(full_text)

            # Build metadata for PDF type
            metadata = {
                "model_used": prompt.model,
                "character_count": total_characters,
                "token_count": token_count
            }

            # Use centralized build_processed_output for consistent format
            processed_content = build_processed_output(
                pages=pages,
                source_type="PDF",
                source_name=pdf_path.name,
                metadata=metadata
            )

            # Upload processed content to Supabase Storage
            storage_path = storage_service.upload_processed_file(
                project_id=project_id,
                source_id=source_id,
                content=processed_content
            )

            if not storage_path:
                raise Exception("Failed to upload processed content to Supabase Storage")

            logger.info("PDF extraction complete: %d pages, %d input tokens, %d output tokens",
                        total_pages, total_input_tokens, total_output_tokens)

            return {
                "success": True,
                "status": "ready",
                "extracted_text_path": storage_path,
                "total_pages": total_pages,
                "pages_processed": total_pages,
                "character_count": total_characters,
                "token_usage": {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens
                },
                "model_used": prompt.model,
                "extracted_at": datetime.now().isoformat(),
                "extraction_method": "batched_tool_based",
                "batch_size": DEFAULT_BATCH_SIZE,
                "total_batches": total_batches,
                "parallel_workers": max_workers,
                "errors": None
            }

        except CancelledException:
            # Cleanup handled by Supabase Storage - no local files to delete
            return {
                "success": False,
                "status": "cancelled",
                "error": "Processing cancelled by user"
            }

        except FileNotFoundError as e:
            logger.error("PDF file not found: %s", e)
            return {
                "success": False,
                "status": "error",
                "error": f"File not found: {str(e)}"
            }

        except Exception as e:
            logger.exception("PDF extraction failed")
            # Cleanup handled by Supabase Storage - no local files to delete
            return {
                "success": False,
                "status": "error",
                "error": str(e)
            }


# Singleton instance for easy import
pdf_service = PDFService()
