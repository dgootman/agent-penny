import chainlit as cl
from chainlit.oauth_providers import GoogleOAuthProvider


class ExtendedGoogleOAuthProvider(GoogleOAuthProvider):
    def __init__(self):
        super().__init__()

        # Add Gmail and Calendar to authentication scope
        self.authorize_params["scope"] = " ".join(
            {
                *self.authorize_params["scope"].split(" "),
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/calendar.readonly",
                "https://www.googleapis.com/auth/calendar.events.owned",
            }
        )

        # Add consent prompt to receive refresh token
        self.authorize_params["prompt"] = "consent"

        self.refresh_token = None

    async def get_raw_token_response(self, code: str, url: str) -> dict:
        if self.refresh_token is not None:
            raise RuntimeError("Refresh token shouldn't be set")

        response = await super().get_raw_token_response(code, url)
        self.refresh_token = response["refresh_token"]

        return response

    async def get_user_info(self, token: str) -> tuple[dict[str, str], cl.User]:
        if self.refresh_token is None:
            raise RuntimeError("Refresh token not set")

        (google_user, user) = await super().get_user_info(token)

        user.metadata["token"] = token
        user.metadata["refresh_token"] = self.refresh_token

        self.refresh_token = None

        return google_user, user
