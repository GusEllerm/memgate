"""ALCF Inference Service Globus auth helper.

Vendored from https://github.com/argonne-lcf/inference-endpoints
(`inference_auth_token.py`, MIT-licensed). The constants below
(client IDs, scope, identity-provider policy) are the public
identifiers published by ALCF and must match upstream exactly.

Run interactively to authenticate:

    uv run smbench-alcf-auth authenticate

Tokens land in `~/.globus/app/<AUTH_CLIENT_ID>/inference_app/tokens.json`
and are reused (with automatic refresh) by `get_access_token()`. The
refresh token is valid for 6 months of inactivity; after that
re-authenticate via the command above.
"""

from __future__ import annotations

import os.path
import time

import globus_sdk
from globus_sdk.login_flows import LocalServerLoginFlowManager  # noqa: F401  # registers globus_sdk.gare


APP_NAME = "inference_app"
AUTH_CLIENT_ID = "58fdd3bc-e1c3-4ce5-80ea-8d6b87cfb944"
GATEWAY_CLIENT_ID = "681c10cc-f684-4540-bcd7-0b4df3bc26ef"
GATEWAY_SCOPE = f"https://auth.globus.org/scopes/{GATEWAY_CLIENT_ID}/action_all"

TOKENS_PATH = (
    f"{os.path.expanduser('~')}/.globus/app/{AUTH_CLIENT_ID}/{APP_NAME}/tokens.json"
)

GA_PARAMS = globus_sdk.gare.GlobusAuthorizationParameters(
    session_required_policies=["83732ff2-9c42-4548-b5ce-17e498c84f6a"]
)


class DomainBasedErrorHandler:
    def __call__(self, app: globus_sdk.UserApp, error: Exception) -> None:
        print(f"Encountered error '{error}', initiating login...")
        app.login(auth_params=GA_PARAMS)


def get_auth_object(force: bool = False) -> globus_sdk.RefreshTokenAuthorizer:
    """Build a Globus UserApp + authorizer; trigger login if needed."""
    app = globus_sdk.UserApp(
        APP_NAME,
        client_id=AUTH_CLIENT_ID,
        scope_requirements={GATEWAY_CLIENT_ID: [GATEWAY_SCOPE]},
        config=globus_sdk.GlobusAppConfig(
            request_refresh_tokens=True,
            token_validation_error_handler=DomainBasedErrorHandler(),
        ),
    )
    if force:
        app.login(auth_params=GA_PARAMS)
    return app.get_authorizer(GATEWAY_CLIENT_ID)


def get_access_token() -> str:
    """Return a current valid access token, refreshing if necessary."""
    auth = get_auth_object(force=False)
    auth.ensure_valid_token()
    return auth.access_token


def get_time_until_token_expiration(units: str = "seconds") -> float | str:
    """Return seconds/minutes/hours until the cached access token expires."""
    auth = get_auth_object(force=False)
    delta_t = auth.expires_at - time.time()
    if units == "seconds":
        return round(delta_t, 2)
    if units == "minutes":
        return round(delta_t / 60, 2)
    if units == "hours":
        return round(delta_t / 3600, 2)
    return "Error: units must be 'seconds', 'minutes', or 'hours'."


def main() -> None:
    import argparse

    class InferenceAuthError(Exception):
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["authenticate", "get_access_token", "get_time_until_token_expiration"])
    parser.add_argument("--units", choices=["seconds", "minutes", "hours"], default="seconds")
    parser.add_argument("-f", "--force", action="store_true", help="re-authenticate from scratch")
    args = parser.parse_args()

    if args.action == "authenticate":
        _ = get_auth_object(force=True)
        print(f"Tokens cached at {TOKENS_PATH}")
        return
    if not os.path.isfile(TOKENS_PATH):
        raise InferenceAuthError("No cached tokens. Run: uv run smbench-alcf-auth authenticate")
    if args.action == "get_access_token":
        if args.force:
            raise InferenceAuthError("--force is not supported with get_access_token")
        print(get_access_token())
    else:
        print(get_time_until_token_expiration(args.units))


if __name__ == "__main__":
    main()
