"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class MixpanelJqlInput(ContractModel):
    script: str = Field(description="JQL JavaScript source. Example: `function main() { return Events({from_date: '2026-01-01', to_date: '2026-01-31'}).groupBy(['name'], mixpanel.reducer.count()); }`")
class MixpanelListEventsInput(ContractModel):
    limit: Optional[int] = Field(default=None, description='Maximum number of event names to return (default: 100, max: 255)')
class MixpanelListFunnelsInput(ContractModel):
    pass
class MixpanelQueryEventsInput(ContractModel):
    event_names: list[str] = Field(description='List of event names to query (e.g. ["Signed Up", "Purchase"])')
    from_date: str = Field(description='Start date inclusive (YYYY-MM-DD)')
    to_date: str = Field(description='End date inclusive (YYYY-MM-DD)')
    unit: Optional[Literal['minute', 'hour', 'day', 'week', 'month']] = Field(default=None, description='Time bucket size (default: day)')
class MixpanelQueryFunnelInput(ContractModel):
    from_date: str = Field(description='Start date inclusive (YYYY-MM-DD)')
    funnel_id: int = Field(description='Numeric funnel ID (from mixpanel_list_funnels)')
    to_date: str = Field(description='End date inclusive (YYYY-MM-DD)')
    unit: Optional[Literal['day', 'week', 'month']] = Field(default=None, description='Time bucket size (default: day)')
class MixpanelRetentionInput(ContractModel):
    born_event: str = Field(description='Cohort-defining event (e.g. "Signed Up")')
    event: Optional[str] = Field(default=None, description='Return event to measure (e.g. "App Opened"). Omit to use any activity.')
    from_date: str = Field(description='Start date inclusive (YYYY-MM-DD)')
    retention_type: Optional[Literal['birth', 'compounded']] = Field(default=None, description='birth = first-time cohort (default), compounded = recurring cohort')
    to_date: str = Field(description='End date inclusive (YYYY-MM-DD)')
    unit: Optional[Literal['day', 'week', 'month']] = Field(default=None, description='Retention bucket size (default: day)')
class MixpanelSegmentationInput(ContractModel):
    event: str = Field(description='Event name to segment (e.g. "Signed Up")')
    from_date: str = Field(description='Start date inclusive (YYYY-MM-DD)')
    on: Optional[str] = Field(default=None, description='Property expression to segment on, e.g. \'properties["$country_code"]\' or \'properties["plan"]\'')
    to_date: str = Field(description='End date inclusive (YYYY-MM-DD)')
    unit: Optional[Literal['minute', 'hour', 'day', 'week', 'month']] = Field(default=None, description='Time bucket size (default: day)')
    where: Optional[str] = Field(default=None, description='Optional filter expression, e.g. \'properties["$country_code"] == "US"\'')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='mixpanel_jql',
        description="Run a Mixpanel JQL (JavaScript Query Language) script for arbitrary custom queries. Use this ONLY when other tools can't express the question (e.g. complex joins, multi-step pipelines). Your script must return a JSON-serializable value via the final `return` from Events/People pipelines.",
        input_model=MixpanelJqlInput,
        terminates_run=False,
        metadata={'registry_name': 'mixpanel_jql'},
    ),
    LocalToolSpec(
        name='mixpanel_list_events',
        description='List event names being tracked in the connected Mixpanel project. Use this first to discover what events are available before running queries. Returns up to `limit` event name strings sorted by recency.',
        input_model=MixpanelListEventsInput,
        terminates_run=False,
        metadata={'registry_name': 'mixpanel_list_events'},
    ),
    LocalToolSpec(
        name='mixpanel_list_funnels',
        description="List funnels configured in the Mixpanel project. Use this to discover funnel IDs before querying a specific funnel's conversion data.",
        input_model=MixpanelListFunnelsInput,
        terminates_run=False,
        metadata={'registry_name': 'mixpanel_list_funnels'},
    ),
    LocalToolSpec(
        name='mixpanel_query_events',
        description="Get time-bucketed counts for one or more events from Mixpanel. Use this to answer questions like 'how many Signups happened last week?' Returns a per-date count per event. Dates must be in YYYY-MM-DD format.",
        input_model=MixpanelQueryEventsInput,
        terminates_run=False,
        metadata={'registry_name': 'mixpanel_query_events'},
    ),
    LocalToolSpec(
        name='mixpanel_query_funnel',
        description='Get conversion data for a specific funnel over a date range. Call mixpanel_list_funnels first to find the funnel_id.',
        input_model=MixpanelQueryFunnelInput,
        terminates_run=False,
        metadata={'registry_name': 'mixpanel_query_funnel'},
    ),
    LocalToolSpec(
        name='mixpanel_retention',
        description="Compute retention: given a cohort of users who did `born_event`, how many came back and did `event` in subsequent buckets. Use for questions like 'what's our weekly retention for new signups?'",
        input_model=MixpanelRetentionInput,
        terminates_run=False,
        metadata={'registry_name': 'mixpanel_retention'},
    ),
    LocalToolSpec(
        name='mixpanel_segmentation',
        description='Segment a single event by a property over a time range. Use this for questions like \'Signups by country in Jan 2026\' or \'Purchases by plan over last 30 days\'. The `on` expression must use Mixpanel\'s property-expression syntax (e.g. properties["$country_code"]).',
        input_model=MixpanelSegmentationInput,
        terminates_run=False,
        metadata={'registry_name': 'mixpanel_segmentation'},
    ),
)
