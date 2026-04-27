import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CitationBadge } from '../components/chat/CitationBadge';
import { sourcesAPI } from '../lib/api/sources';

describe('CitationBadge', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches and renders citation content on hover', async () => {
    const user = userEvent.setup();
    vi.spyOn(sourcesAPI, 'getCitationContent').mockResolvedValue({
      content: 'Quoted source content',
      chunk_id: 'source-1_page_2_chunk_1',
      source_id: 'source-1',
      source_name: 'Source One',
      page_number: 2,
      chunk_index: 1,
    });

    render(
      <CitationBadge
        citationNumber={1}
        chunkId="source-1_page_2_chunk_1"
        sourceId="source-1"
        pageNumber={2}
        projectId="proj-1"
      />
    );

    await user.hover(screen.getByText('1'));

    await waitFor(() => {
      expect(sourcesAPI.getCitationContent).toHaveBeenCalledWith(
        'proj-1',
        'source-1_page_2_chunk_1'
      );
    });
    await waitFor(() => {
      expect(screen.getByText('Quoted source content')).toBeTruthy();
    });
  });
});
