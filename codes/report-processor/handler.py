import json
import os
import logging
from datetime import datetime
import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
sns = boto3.client("sns")
ses = boto3.client("ses")
rds_data = boto3.client("rds-data")
dynamodb = boto3.resource("dynamodb")

REPORTS_BUCKET = os.environ["REPORTS_BUCKET"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
DYNAMODB_EVENTS_TABLE = os.environ["DYNAMODB_EVENTS_TABLE"]
DYNAMODB_SEATS_TABLE = os.environ["DYNAMODB_SEATS_TABLE"]
AURORA_CLUSTER_ARN = os.environ["AURORA_CLUSTER_ARN"]
AURORA_SECRET_ARN = os.environ["AURORA_SECRET_ARN"]
AURORA_DB_NAME = os.environ["AURORA_DB_NAME"]

events_table = dynamodb.Table(DYNAMODB_EVENTS_TABLE)
seats_table = dynamodb.Table(DYNAMODB_SEATS_TABLE)

def lambda_handler(event, context):
    logger.info("Procesando mensajes de SQS para generación de reportes")

    for record in event.get("Records", []):
        try:
            # 1. Body del mensaje SQS
            body = json.loads(record["body"])

            # 2. EventBridge envía el evento dentro del body
            detail = body.get("detail", {})

            event_id = detail.get("event_id")
            organizer_id = detail.get("organizer_id")
            organizer_email = detail.get("organizer_email", "")
            report_type = detail.get("report_type", "general")
            requested_at = detail.get("requested_at")

            logger.info(f"Generando reporte: {report_type} para event_id={event_id}")

            # 3. Generar reporte (mock)
            report_data = generate_report(event_id, organizer_id, report_type)

            # 4. Nombre del archivo en S3
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            key = f"reports/{organizer_id}/{event_id}/{report_type}_{timestamp}.json"

            # 5. Guardar en S3
            s3.put_object(
                Bucket=REPORTS_BUCKET,
                Key=key,
                Body=json.dumps(report_data),
                ContentType="application/json"
            )

            logger.info(f"Reporte guardado en s3://{REPORTS_BUCKET}/{key}")

            # Generar URL prefirmada con expiracion de 24 horas
            presigned_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": REPORTS_BUCKET, "Key": key},
                ExpiresIn=86400,
            )

            # 6. Notificar al organizador vía SNS
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject="Reporte generado",
                Message=json.dumps({
                    "message": "Tu reporte está listo",
                    "event_id": event_id,
                    "report_type": report_type,
                    "download_url": presigned_url
                }, indent=2)
            )

            # =========================
            # SES EMAIL (al correo del organizador desde el JWT)
            # =========================
            if organizer_email:
                ses.send_email(
                    Source=organizer_email,
                    Destination={
                        "ToAddresses": [organizer_email]
                    },
                    Message={
                        "Subject": {"Data": "Reporte listo"},
                        "Body": {
                            "Text": {
                                "Data": f"Tu reporte {report_type} ya está disponible.\n\nDescarga tu reporte aquí (válido por 24 horas):\n{presigned_url}"
                            }
                        }
                    }
                )

        except Exception as e:
            logger.error(f"Error procesando mensaje: {str(e)}")
            raise e  # importante para retry / DLQ

    return {"status": "processed"}


# =========================
# Generador de reportes
# =========================

def generate_report(event_id, organizer_id, report_type):
    """
    Genera reportes reales consultando DynamoDB (asientos) y Aurora (eventos, ubicaciones).
    """

    base = {
        "event_id": event_id,
        "organizer_id": organizer_id,
        "generated_at": datetime.utcnow().isoformat(),
        "report_type": report_type,
    }

    # Obtener todos los asientos del evento desde DynamoDB
    seats = query_all_seats(event_id)

    if report_type == "attendance":
        base["data"] = build_attendance_report(event_id, seats)

    elif report_type == "sales":
        base["data"] = build_sales_report(event_id, seats)

    elif report_type == "occupancy":
        base["data"] = build_occupancy_report(event_id, seats)

    else:  # general
        base["data"] = build_general_report(event_id, organizer_id, seats)

    return base


def query_all_seats(event_id):
    """Consulta todos los asientos de un evento en DynamoDB con paginación."""
    items = []
    kwargs = {
        "KeyConditionExpression": Key("event_id").eq(event_id)
    }
    while True:
        response = seats_table.query(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return items


def query_aurora(sql, parameters=None):
    """Ejecuta una consulta en Aurora via Data API y retorna los registros."""
    params = {
        "resourceArn": AURORA_CLUSTER_ARN,
        "secretArn": AURORA_SECRET_ARN,
        "database": AURORA_DB_NAME,
        "sql": sql,
        "includeResultMetadata": True,
    }
    if parameters:
        params["parameters"] = parameters

    response = rds_data.execute_statement(**params)

    columns = [col["name"] for col in response["columnMetadata"]]
    rows = []
    for record in response["records"]:
        row = {}
        for i, field in enumerate(record):
            if "stringValue" in field:
                row[columns[i]] = field["stringValue"]
            elif "longValue" in field:
                row[columns[i]] = field["longValue"]
            elif "doubleValue" in field:
                row[columns[i]] = field["doubleValue"]
            elif "booleanValue" in field:
                row[columns[i]] = field["booleanValue"]
            elif "isNull" in field and field["isNull"]:
                row[columns[i]] = None
            else:
                row[columns[i]] = str(field)
        rows.append(row)
    return rows


def get_event_from_aurora(event_id):
    """Obtiene la información del evento y su ubicación desde Aurora."""
    sql = """
        SELECT e.id, e.name, e.description, e.event_date, e.event_time,
               e.total_seats, e.status, e.organizer_id,
               l.name AS location_name, l.city, l.capacity AS location_capacity
        FROM events e
        LEFT JOIN locations l ON e.location_id = l.id
        WHERE e.id = :event_id
    """
    parameters = [{"name": "event_id", "value": {"stringValue": event_id}}]
    rows = query_aurora(sql, parameters)
    return rows[0] if rows else None


def build_attendance_report(event_id, seats):
    """Reporte de asistencia: total asistentes, check-ins, reservados, cancelados."""
    total = len(seats)
    status_counts = {}
    for seat in seats:
        status = seat.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    checked_in = status_counts.get("checked_in", 0)
    reserved = status_counts.get("reserved", 0)
    confirmed = status_counts.get("confirmed", 0)
    cancelled = status_counts.get("cancelled", 0)
    available = status_counts.get("available", 0)

    total_attendees = checked_in + confirmed + reserved

    return {
        "total_seats": total,
        "total_attendees": total_attendees,
        "checked_in": checked_in,
        "confirmed": confirmed,
        "reserved": reserved,
        "cancelled": cancelled,
        "available": available,
        "attendance_rate": f"{round((checked_in / total * 100), 1)}%" if total > 0 else "0%",
        "status_breakdown": status_counts,
    }


def build_sales_report(event_id, seats):
    """Reporte de ventas: tickets vendidos, ingresos, desglose por estado."""
    sold_statuses = {"reserved", "confirmed", "checked_in"}
    sold_seats = [s for s in seats if s.get("status") in sold_statuses]
    tickets_sold = len(sold_seats)

    revenue = sum(float(s.get("price", 0)) for s in sold_seats)
    total_possible_revenue = sum(float(s.get("price", 0)) for s in seats)

    return {
        "tickets_sold": tickets_sold,
        "total_seats": len(seats),
        "revenue": revenue,
        "total_possible_revenue": total_possible_revenue,
        "sell_through_rate": f"{round((tickets_sold / len(seats) * 100), 1)}%" if seats else "0%",
    }


def build_occupancy_report(event_id, seats):
    """Reporte de ocupación: capacidad del venue vs asientos ocupados."""
    event_info = get_event_from_aurora(event_id)

    location_capacity = 0
    location_name = "Desconocida"
    if event_info:
        location_capacity = event_info.get("location_capacity", 0) or 0
        location_name = event_info.get("location_name", "Desconocida")

    occupied_statuses = {"reserved", "confirmed", "checked_in"}
    occupied = len([s for s in seats if s.get("status") in occupied_statuses])
    total_seats = len(seats)
    capacity = location_capacity if location_capacity > 0 else total_seats

    return {
        "location": location_name,
        "location_capacity": location_capacity,
        "total_seats_configured": total_seats,
        "occupied": occupied,
        "available": total_seats - occupied,
        "occupancy_rate": f"{round((occupied / capacity * 100), 1)}%" if capacity > 0 else "0%",
    }


def build_general_report(event_id, organizer_id, seats):
    """Reporte general: información del evento + resumen de asientos + alertas."""
    event_info = get_event_from_aurora(event_id)

    # Contar alertas del evento
    alerts_sql = """
        SELECT COUNT(*) AS total_alerts FROM alerts
        WHERE event_id = :event_id AND organizer_id = :organizer_id
    """
    alerts_params = [
        {"name": "event_id", "value": {"stringValue": event_id}},
        {"name": "organizer_id", "value": {"stringValue": organizer_id}},
    ]
    alerts_rows = query_aurora(alerts_sql, alerts_params)
    total_alerts = alerts_rows[0].get("total_alerts", 0) if alerts_rows else 0

    status_counts = {}
    for seat in seats:
        status = seat.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    occupied_statuses = {"reserved", "confirmed", "checked_in"}
    occupied = len([s for s in seats if s.get("status") in occupied_statuses])

    report = {
        "summary": "Reporte general del evento",
        "total_seats": len(seats),
        "occupied": occupied,
        "available": len(seats) - occupied,
        "status_breakdown": status_counts,
        "total_alerts": total_alerts,
    }

    if event_info:
        report["event_name"] = event_info.get("name")
        report["event_date"] = event_info.get("event_date")
        report["event_time"] = event_info.get("event_time")
        report["event_status"] = event_info.get("status")
        report["location"] = event_info.get("location_name")
        report["city"] = event_info.get("city")

    return report