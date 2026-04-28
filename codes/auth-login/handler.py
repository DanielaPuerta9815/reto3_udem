import json
import os
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

cognito = boto3.client("cognito-idp")

CLIENT_ID = os.environ["CLIENT_ID"]


def lambda_handler(event, context):
    """Autentica un usuario y retorna los tokens JWT (IdToken, AccessToken, RefreshToken)."""
    logger.info("POST /auth/login - Inicio de sesion")

    try:
        body = json.loads(event.get("body", "{}"))
        email = body.get("email")
        password = body.get("password")

        if not all([email, password]):
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "email y password son requeridos"}),
            }

        # Autenticar con Cognito usando USER_PASSWORD_AUTH
        response = cognito.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": email,
                "PASSWORD": password,
            },
        )

        auth_result = response.get("AuthenticationResult", {})

        logger.info(f"Login exitoso: {email}")

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({
                "message": "Login exitoso",
                "tokens": {
                    "id_token": auth_result.get("IdToken"),
                    "access_token": auth_result.get("AccessToken"),
                    "refresh_token": auth_result.get("RefreshToken"),
                    "expires_in": auth_result.get("ExpiresIn"),
                    "token_type": auth_result.get("TokenType"),
                },
            }),
        }

    except cognito.exceptions.NotAuthorizedException:
        return {
            "statusCode": 401,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Credenciales incorrectas"}),
        }

    except cognito.exceptions.UserNotFoundException:
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Usuario no encontrado"}),
        }

    except cognito.exceptions.UserNotConfirmedException:
        return {
            "statusCode": 403,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "El usuario no ha sido confirmado"}),
        }

    except Exception as e:
        logger.error(f"Error al iniciar sesion: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al iniciar sesion"}),
        }
