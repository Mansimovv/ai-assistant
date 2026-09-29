from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from app.api.deps import get_tool_registry
from app.schemas.tools import ToolExecuteRequest, ToolExecuteResponse, ToolInfo
from app.tools.registry import ConfirmationRequiredError, ToolNotFoundError, ToolRegistry

router = APIRouter(tags=["tools"])

RegistryDep = Annotated[ToolRegistry, Depends(get_tool_registry)]


@router.get("/tools")
async def list_tools(registry: RegistryDep) -> list[ToolInfo]:
    return [
        ToolInfo(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters.model_json_schema(),
            permission=tool.permission,
            requires_confirmation=tool.requires_confirmation,
        )
        for tool in registry.list_tools()
    ]


@router.post("/tools/{name}/execute")
async def execute_tool(name: str, request: ToolExecuteRequest, registry: RegistryDep) -> ToolExecuteResponse:
    try:
        result = await registry.execute(name, request.arguments, confirmed=request.confirmed)
    except ToolNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown tool: {name}") from exc
    except ConfirmationRequiredError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Tool {name!r} requires confirmation") from exc
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, exc.errors(include_url=False, include_context=False)
        ) from exc
    return ToolExecuteResponse(tool=name, result=result)
