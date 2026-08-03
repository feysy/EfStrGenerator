import json
import os
import traceback
import pika

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


def publish_job_to_queue(job_id: str) -> None:
    """Publishes a job ID to the transcription_jobs RabbitMQ queue."""
    try:
        parameters = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.queue_declare(queue="transcription_jobs", durable=True)
        channel.basic_publish(
            exchange="",
            routing_key="transcription_jobs",
            body=json.dumps({"job_id": job_id}),
            properties=pika.BasicProperties(delivery_mode=2),  # persistent
        )
        connection.close()
    except Exception as e:
        traceback.print_exc()
        print(f"Error publishing job to RabbitMQ: {e}")
