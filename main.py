import os
import json
import uvicorn

from typing import Dict, Any

from a2a.server.tasks import InMemoryTaskStore
from a2a.server.apps import A2AStarletteApplication
from a2a.types import (
    AgentCard,
    AgentProvider,
    AgentSkill,
    AgentCapabilities,
)
from a2a.utils import new_agent_text_message
from a2a.utils.errors import ServerError, UnsupportedOperationError
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler, RequestHandler


class ListFilesAgentExecutor(AgentExecutor):
    """A2A Agent Executor template for building agent-to-agent applications."""

    def __init__(self):
        super().__init__()

    def get_task_updater(self, context: RequestContext, event_queue: EventQueue) -> TaskUpdater | None:
        if context.context_id and context.task_id:
            task_updater = TaskUpdater(event_queue=event_queue, context_id=context.context_id, task_id=context.task_id)
        else:
            task_updater = None

        return task_updater

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute method required by AgentExecutor interface."""
        task_updater = self.get_task_updater(context, event_queue)

        try:

            # Extract task information from context
            message_parts = context.message.parts if context.message else []
            task_data = {}
            task_type = "list_files"

            # Parse message content to extract task type and data
            if message_parts and len(message_parts) > 0:
                if hasattr(message_parts[0].root, "text"):
                    try:
                        # Try to parse as JSON for structured requests
                        parsed_data = json.loads(message_parts[0].root.text)
                        task_type = parsed_data.get("task_type", "list_files")
                        task_data = parsed_data.get("data", {})
                    except (json.JSONDecodeError, AttributeError):
                        # Handle as plain text request
                        task_data = {"message": message_parts[0].root.text}

            # Process the task
            result = await self._handle_task(task_type, task_data, context.metadata)
            result_message = new_agent_text_message(json.dumps(result, indent=2), context_id=context.context_id, task_id=context.task_id)
            
            await event_queue.enqueue_event(
                result_message
            )

            if task_updater:
                await task_updater.complete()

        except Exception as e:
            error_message = new_agent_text_message(f"Error: {str(e)}")
            
            await event_queue.enqueue_event(error_message)

            if task_updater:
                await task_updater.failed()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())

    async def _handle_task(
        self, task_type: str, data: Dict[str, Any], metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle different task types - customize this method for your agent."""
        if task_type == "list_files":
            return await self._list_files(data, metadata)
        else:
            return {"error": f"Unknown task type: {task_type}"}

    async def _list_files(self, data: Dict[str, Any], metadata: dict[str, Any]) -> Dict[str, Any]:
        """Template implementation - replace with your agent logic."""
        message = data.get("message", "No message provided")

        # Your custom agent logic goes here
        result = (
            f'Your user id is {metadata.get("user_id", "unknown")}' + "\n" + \
            f'Your thread id is {metadata.get("thread_id", "unknown")}' + "\n\n" + \
            " FILE LIST: " + "\n" +
            "sample_document.doc" + "\n" +
            "foo.pptx"
        )

        return result


# Create agent card
agent_card = AgentCard(
    name="ListFilesAgent",
    description="A2A agent that can list the files in this chat",
    version="1.0.0",
    url=os.getenv("HU_APP_URL") or "",  # Provide empty string as fallback
    capabilities=AgentCapabilities(
        streaming=True, push_notifications=False, state_transition_history=True
    ),
    skills=[
        AgentSkill(
            id="list_files",
            name="List files",
            description="Pull files from navigator and return them in a bulleted list",
            tags=["template", "processing", "a2a"],
            examples=["What files have been uploaded into this conversation?"],
            input_modes=["application/json", "text/plain"],
            output_modes=["application/json", "text/plain"],
        )
    ],
    default_input_modes=["application/json", "text/plain"],
    default_output_modes=["text/plain"],
    provider=AgentProvider(
        organization="Health Universe",
        url="https://www.healthuniverse.com",
    ),
)

# Create the A2A Starlette application
agent_executor = ListFilesAgentExecutor()

request_handler = DefaultRequestHandler(
    agent_executor=agent_executor,
    task_store=InMemoryTaskStore(),
)
app = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler).build()

if __name__ == "__main__":

    uvicorn.run(app, host="0.0.0.0", port=8000)
