from confluent_kafka import Producer, KafkaException
from django.conf import settings
import json
import logging
import socket

logger = logging.getLogger(__name__)

def get_kafka_producer():
    """
    إنشاء وإرجاع منتج Kafka.
    """
    try:
        logger.info(f"محاولة الاتصال بـ Kafka على العنوان: {settings.KAFKA_BOOTSTRAP_SERVERS}")
        producer = Producer(settings.KAFKA_CONFIG)
        
        # اختبار الاتصال
        producer.list_topics(timeout=10)
        logger.info("تم الاتصال بـ Kafka بنجاح")
        return producer
    except KafkaException as ke:
        logger.error(f"خطأ Kafka: {ke}")
        return None
    except socket.gaierror as se:
        logger.error(f"خطأ في حل العنوان: {se}")
        return None
    except Exception as e:
        logger.error(f"فشل في إنشاء منتج Kafka: {e}")
        return None

def delivery_report(err, msg):
    """
    تقرير تسليم الرسالة لـ Kafka.
    """
    if err is not None:
        logger.error(f"فشل في تسليم الرسالة: {err}")
    else:
        logger.info(f"تم تسليم الرسالة إلى {msg.topic()} [{msg.partition()}] في الموضع {msg.offset()}")

def send_success_message_to_kafka(job_data):
    """
    إرسال رسالة نجاح إلى Kafka.
    
    Args:
        job_data: بيانات المهمة الناجحة (قاموس)
    """
    producer = get_kafka_producer()
    if not producer:
        logger.error("لم يتم إرسال رسالة النجاح إلى Kafka: لا يمكن إنشاء المنتج")
        return False
    
    try:
        # تحويل البيانات إلى JSON
        message_value = json.dumps(job_data).encode('utf-8')
        
        logger.info(f"محاولة إرسال رسالة إلى موضوع {settings.KAFKA_SUCCESS_TOPIC}")
        
        # إرسال الرسالة إلى موضوع النجاح
        producer.produce(
            topic=settings.KAFKA_SUCCESS_TOPIC,
            value=message_value,
            callback=delivery_report
        )
        
        # ضمان إرسال جميع الرسائل
        logger.info("انتظار إرسال الرسائل...")
        remaining = producer.flush(timeout=10)
        
        if remaining > 0:
            logger.warning(f"لم يتم إرسال {remaining} رسائل خلال المهلة المحددة")
            return False
        
        logger.info(f"تم إرسال رسالة نجاح إلى Kafka للمهمة {job_data.get('job_id')}")
        return True
    except KafkaException as ke:
        logger.error(f"خطأ Kafka أثناء إرسال الرسالة: {ke}")
        return False
    except Exception as e:
        logger.error(f"خطأ في إرسال رسالة النجاح إلى Kafka: {e}")
        return False
