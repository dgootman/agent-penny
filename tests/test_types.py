from pydantic_ai import Tool


def test_annotations():
    from agent_penny.types import CreateCalendarEventRequest

    def calendar_create_event(request: CreateCalendarEventRequest) -> None:
        pass

    tool = Tool(calendar_create_event)
    assert tool.name == "calendar_create_event"
    assert "Request to create a calendar event." in tool.description
    assert (
        "Start and end times are either full dates (for all-day events) or date, time, and timezone (for non-all-day events)."
        in tool.description
    )
