import json
import os
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

cognito = boto3.client("cognito-idp")
rds_client = boto3.client("rds-data")

USER_POOL_ID = os.environ["USER_POOL_ID"]
CLIENT_ID = os.environ["CLIENT_ID"]
AURORA_CLUSTER_ARN = os.environ.get("AURORA_CLUSTER_ARN", "")
AURORA_SECRET_ARN = os.environ.get("AURORA_SECRET_ARN", "")
AURORA_DB_NAME = os.environ.get("AURORA_DB_NAME", "")


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

        # 4. Obtener el sub (ID único) del usuario recién creado
        user_info = cognito.admin_get_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
        )
        user_sub = ""
        for attr in user_info.get("UserAttributes", []):
            if attr["Name"] == "sub":
                user_sub = attr["Value"]
                break

        # 5. Si es ORGANIZER, registrar en la tabla organizers de Aurora
        if group == "ORGANIZER" and AURORA_CLUSTER_ARN:
            name = body.get("name", email)
            rds_client.execute_statement(
                resourceArn=AURORA_CLUSTER_ARN,
                secretArn=AURORA_SECRET_ARN,
                database=AURORA_DB_NAME,
                sql="""
                    INSERT INTO organizers (id, name, email)
                    VALUES (:id, :name, :email)
                """,
                parameters=[
                    {"name": "id", "value": {"stringValue": user_sub}},
                    {"name": "name", "value": {"stringValue": name}},
                    {"name": "email", "value": {"stringValue": email}},
                ],
            )
            logger.info(f"Organizador registrado en Aurora: {user_sub}")

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
