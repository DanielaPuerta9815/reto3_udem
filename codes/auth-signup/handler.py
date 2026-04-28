import json
import os
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

cognito = boto3.client("cognito-idp")

USER_POOL_ID = os.environ["USER_POOL_ID"]
CLIENT_ID = os.environ["CLIENT_ID"]


def lambda_handler(event, context):
    """Registra un nuevo usuario en Cognito, lo confirma y lo asigna a un grupo."""
    logger.info("POST /auth/signup - Registro de usuario")

    try:
        body = json.loads(event.get("body", "{}"))
        email = body.get("email")
        password = body.get("password")
        group = body.get("group", "ATTENDEE")

        if not all([email, password]):
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "email y password son requeridos"}),
            }

        valid_groups = ["ATTENDEE", "ORGANIZER"]
        if group not in valid_groups:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({
                    "error": f"group invalido. Valores permitidos: {', '.join(valid_groups)}"
                }),
            }

        # 1. Registrar usuario en Cognito
        cognito.sign_up(
            ClientId=CLIENT_ID,
            Username=email,
            Password=password,
            UserAttributes=[
                {"Name": "email", "Value": email},
            ],
        )

        # 2. Confirmar usuario automaticamente (sin verificacion por correo)
        cognito.admin_confirm_sign_up(
            UserPoolId=USER_POOL_ID,
            Username=email,
        )

        # 3. Asignar al grupo correspondiente
        cognito.admin_add_user_to_group(
            UserPoolId=USER_POOL_ID,
            Username=email,
            GroupName=group,
        )

        logger.info(f"Usuario registrado: {email}, grupo: {group}")

        return {
            "statusCode": 201,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({
                "message": "Usuario registrado exitosamente",
                "user": {
                    "email": email,
                    "group": group,
                    "confirmed": True,
                },
            }),
        }

    except cognito.exceptions.UsernameExistsException:
        return {
            "statusCode": 409,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "El usuario ya existe"}),
        }

    except cognito.exceptions.InvalidPasswordException as e:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": f"Password invalido: {str(e)}"}),
        }

    except Exception as e:
        logger.error(f"Error al registrar usuario: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al registrar el usuario"}),
        }
