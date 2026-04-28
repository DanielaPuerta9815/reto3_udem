import json
import os
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

SEATS_TABLE = os.environ["DYNAMODB_SEATS_TABLE"]
SOCKETS_TABLE = os.environ["DYNAMODB_SOCKETS_TABLE"]
WEBSOCKET_CALLBACK_URL = os.environ["WEBSOCKET_CALLBACK_URL"]


def lambda_handler(event, context):
    """
    Maneja las conexiones WebSocket ($connect, $disconnect, $default).
    - $connect: registra la conexión en DynamoDB (tabla sockets)
    - $disconnect: elimina la conexión de DynamoDB
    - $default: recibe seat_id, consulta su estado y responde; registra la suscripción
    """
    route_key = event.get("requestContext", {}).get("routeKey")
    connection_id = event.get("requestContext", {}).get("connectionId")

    logger.info(f"WebSocket route={route_key}, connectionId={connection_id}")

    if route_key == "$connect":
        return handle_connect(connection_id, event)
    elif route_key == "$disconnect":
        return handle_disconnect(connection_id)
    elif route_key == "$default":
        return handle_default(connection_id, event)
    else:
        return {"statusCode": 400, "body": "Ruta no soportada"}


def handle_connect(connection_id, event):
    """Registra una nueva conexión WebSocket."""
    try:
        sockets_table = dynamodb.Table(SOCKETS_TABLE)
        query_params = event.get("queryStringParameters") or {}

        sockets_table.put_item(
            Item={
                "connection_id": connection_id,
                "connected_at": event.get("requestContext", {}).get("connectedAt", 0),
                "user_id": query_params.get("user_id", "anonymous"),
                "seat_id": query_params.get("seat_id", ""),
            }
        )

        logger.info(f"Conexion establecida: {connection_id}")
        return {"statusCode": 200, "body": "Connected"}

    except Exception as e:
        logger.error(f"Error en $connect: {str(e)}")
        return {"statusCode": 500, "body": "Error al conectar"}


def handle_disconnect(connection_id):
    """Elimina una conexión WebSocket."""
    try:
        sockets_table = dynamodb.Table(SOCKETS_TABLE)
        sockets_table.delete_item(Key={"connection_id": connection_id})

        logger.info(f"Conexion cerrada: {connection_id}")
        return {"statusCode": 200, "body": "Disconnected"}

    except Exception as e:
        logger.error(f"Error en $disconnect: {str(e)}")
        return {"statusCode": 500, "body": "Error al desconectar"}


def handle_default(connection_id, event):
    """
    Procesa mensajes entrantes del cliente.
    Espera payload: { "action": "getSeatStatus", "seat_id": "...", "event_id": "..." }
    """
    try:
        body = json.loads(event.get("body", "{}"))
        action = body.get("action", "getSeatStatus")
        seat_id = body.get("seat_id")
        event_id = body.get("event_id")

        if not seat_id or not event_id:
            send_to_connection(connection_id, {
                "error": "seat_id y event_id son requeridos",
                "action": action,
            })
            return {"statusCode": 400, "body": "Parametros faltantes"}

        # Registrar la suscripción del cliente a este asiento
        sockets_table = dynamodb.Table(SOCKETS_TABLE)
        sockets_table.update_item(
            Key={"connection_id": connection_id},
            UpdateExpression="SET seat_id = :sid, event_id = :eid",
            ExpressionAttributeValues={
                ":sid": seat_id,
                ":eid": event_id,
            },
        )

        # Consultar estado actual del asiento en DynamoDB
        seats_table = dynamodb.Table(SEATS_TABLE)
        response = seats_table.get_item(
            Key={"event_id": event_id, "seat_id": seat_id}
        )

        seat_data = response.get("Item")

        if not seat_data:
            send_to_connection(connection_id, {
                "action": "seatStatus",
                "seat_id": seat_id,
                "event_id": event_id,
                "status": "not_found",
                "message": "Asiento no encontrado",
            })
            return {"statusCode": 200, "body": "Seat not found"}

        # Enviar el estado actual del asiento al cliente
        seat_status = {
            "action": "seatStatus",
            "seat_id": seat_id,
            "event_id": event_id,
            "status": seat_data.get("status", "available"),
            "section": seat_data.get("section", ""),
            "row": seat_data.get("row", ""),
            "number": seat_data.get("number", ""),
            "price": str(seat_data.get("price", 0)),
        }

        # Si está reservado, no exponer el user_id al consultante
        if seat_data.get("status") == "reserved":
            seat_status["reserved"] = True

        send_to_connection(connection_id, seat_status)

        logger.info(f"Estado del asiento enviado: seat_id={seat_id}, status={seat_data.get('status')}")
        return {"statusCode": 200, "body": "Seat status sent"}

    except json.JSONDecodeError:
        send_to_connection(connection_id, {
            "error": "Payload JSON invalido",
        })
        return {"statusCode": 400, "body": "Invalid JSON"}

    except Exception as e:
        logger.error(f"Error en $default: {str(e)}")
        return {"statusCode": 500, "body": "Error interno"}


def send_to_connection(connection_id, data):
    """Envía un mensaje a un cliente WebSocket conectado."""
    try:
        apigw_management = boto3.client(
            "apigatewaymanagementapi",
            endpoint_url=WEBSOCKET_CALLBACK_URL,
        )
        apigw_management.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(data).encode("utf-8"),
        )
    except apigw_management.exceptions.GoneException:
        logger.warning(f"Conexion {connection_id} ya no existe, limpiando...")
        sockets_table = dynamodb.Table(SOCKETS_TABLE)
        sockets_table.delete_item(Key={"connection_id": connection_id})
    except Exception as e:
        logger.error(f"Error al enviar mensaje a {connection_id}: {str(e)}")
