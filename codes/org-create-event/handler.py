import json
import os
import logging
import uuid
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
rds_client = boto3.client("rds-data")

EVENTS_TABLE = os.environ["DYNAMODB_EVENTS_TABLE"]
SEATS_TABLE = os.environ["DYNAMODB_SEATS_TABLE"]
AURORA_CLUSTER_ARN = os.environ["AURORA_CLUSTER_ARN"]
AURORA_SECRET_ARN = os.environ["AURORA_SECRET_ARN"]
AURORA_DB_NAME = os.environ["AURORA_DB_NAME"]


def lambda_handler(event, context):
    """Crea un evento nuevo para un organizador."""
    logger.info("POST /organizer/events - Crear evento")

    try:
        body = json.loads(event.get("body", "{}"))

        required_fields = ["organizer_id", "name", "event_date", "event_time", "total_seats", "location_id"]
        missing = [f for f in required_fields if not body.get(f)]
        if missing:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": f"Campos requeridos faltantes: {', '.join(missing)}"}),
            }

        event_id = str(uuid.uuid4())

        # Insertar metadata del evento en Aurora
        rds_client.execute_statement(
            resourceArn=AURORA_CLUSTER_ARN,
            secretArn=AURORA_SECRET_ARN,
            database=AURORA_DB_NAME,
            sql="""
                INSERT INTO events (id, organizer_id, name, description, event_date, event_time,
                                    total_seats, location_id, status, created_at)
                VALUES (:id, :organizer_id, :name, :description, :event_date, :event_time,
                        :total_seats, :location_id, 'active', NOW())
            """,
            parameters=[
                {"name": "id", "value": {"stringValue": event_id}},
                {"name": "organizer_id", "value": {"stringValue": body["organizer_id"]}},
                {"name": "name", "value": {"stringValue": body["name"]}},
                {"name": "description", "value": {"stringValue": body.get("description", "")}},
                {"name": "event_date", "value": {"stringValue": body["event_date"]}},
                {"name": "event_time", "value": {"stringValue": body["event_time"]}},
                {"name": "total_seats", "value": {"longValue": int(body["total_seats"])}},
                {"name": "location_id", "value": {"stringValue": body["location_id"]}},
            ],
        )

        # Inicializar contadores en DynamoDB
        events_table = dynamodb.Table(EVENTS_TABLE)
        total_seats = int(body["total_seats"])
        events_table.put_item(
            Item={
                "event_id": event_id,
                "seats_sold": 0,
                "seats_available": total_seats,
                "total_seats": total_seats,
            }
        )

        # Crear asientos iniciales en DynamoDB
        seats_table = dynamodb.Table(SEATS_TABLE)
        with seats_table.batch_writer() as batch:
            for i in range(1, total_seats + 1):
                batch.put_item(
                    Item={
                        "event_id": event_id,
                        "seat_id": f"seat-{i:04d}",
                        "section": body.get("default_section", "general"),
                        "row": str((i - 1) // 10 + 1),
                        "number": str((i - 1) % 10 + 1),
                        "status": "available",
                        "price": str(body.get("price", 0)),
                    }
                )

        logger.info(f"Evento creado: {event_id} por organizador {body['organizer_id']}")

        return {
            "statusCode": 201,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({
                "message": "Evento creado exitosamente",
                "event": {
                    "id": event_id,
                    "name": body["name"],
                    "total_seats": total_seats,
                    "status": "active",
                },
            }),
        }

    except Exception as e:
        logger.error(f"Error al crear evento: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Error interno al crear el evento"}),
        }
