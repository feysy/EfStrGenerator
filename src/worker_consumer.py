import json
import threading
import traceback
import time
import pika

# Force-register Whisper models in Hugging Face's global backend registry
import transformers.models.whisper.modeling_whisper  # noqa: F401
from transformers import WhisperForConditionalGeneration, WhisperProcessor  # noqa: F401

from src.transcription import process_transcription_job

RABBITMQ_URL = __import__("os").getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


def callback(ch, method, properties, body) -> None:
    """
    RabbitMQ message handler.

    process_transcription_job can run for minutes (model load + inference).
    pika's BlockingConnection needs its own thread free to service heartbeats
    during that time, or RabbitMQ will kill the connection as unresponsive.
    The actual work happens on a background thread; only the ack is handed
    back via add_callback_threadsafe.
    """
    def run_job():
        try:
            data = json.loads(body.decode())
            job_id = data.get("job_id")
            if job_id:
                process_transcription_job(job_id)
        except Exception as e:
            traceback.print_exc()
            print(f"Error handling message: {e}")
        finally:
            ch.connection.add_callback_threadsafe(
                lambda: ch.basic_ack(delivery_tag=method.delivery_tag)
            )

    threading.Thread(target=run_job, daemon=True).start()


def main() -> None:
    print("Worker starting up...")

    connection = None
    for attempt in range(10):
        try:
            parameters = pika.URLParameters(RABBITMQ_URL)
            connection = pika.BlockingConnection(parameters)
            break
        except pika.exceptions.AMQPConnectionError:
            print(f"RabbitMQ not ready yet, retrying in 5 s... (attempt {attempt + 1}/10)")
            time.sleep(5)

    if not connection:
        print("Could not connect to RabbitMQ. Exiting.")
        return

    channel = connection.channel()
    channel.queue_declare(queue="transcription_jobs", durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="transcription_jobs", on_message_callback=callback)

    print("Worker is ready and waiting for transcription messages...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    connection.close()
