import os

from chainlit import server
from fastapi.responses import FileResponse, Response
from fastapi.routing import APIRoute
from htpy import a, body, h1, html, li, ul
from htpy.starlette import HtpyResponse

from agent_penny import user_data


def mount():
    # Mount the user data dir to Chainlit's {CHAINLIT_ROOT_PATH}/private path to allow users to access their data
    if not any(
        isinstance(r, APIRoute) and r.name == "agent_penny_user_data"
        for r in server.app.router.routes
    ):

        def get(file_path: str, user: server.UserParam):
            assert user

            user_id = user.identifier

            path = user_data._user_path(user_id, file_path)
            if not path.exists():
                return Response(status_code=404)

            if path.is_dir():
                content = list(path.iterdir())

                return HtpyResponse(
                    html[
                        body[
                            h1[file_path or "/"],
                            ul[
                                (
                                    li[
                                        a(href=f"{p.name}/" if p.is_dir() else p.name)[
                                            f"{p.name}/" if p.is_dir() else p.name
                                        ]
                                    ]
                                    for p in content
                                )
                            ]
                            if content
                            else ("Empty directory"),
                        ]
                    ]
                )

            return FileResponse(path)

        server.app.router.routes.insert(
            0,
            APIRoute(
                os.path.join(
                    os.environ.get("CHAINLIT_ROOT_PATH", "/"),
                    "private/{file_path:path}",
                ),
                get,
                name="agent_penny_user_data",
            ),
        )
