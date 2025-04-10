from django.core.management.base import BaseCommand
from django.conf import settings
from confluent_kafka import Producer, Consumer, KafkaException, admin
import socket
import time
import json
import uuid

class Command(BaseCommand):
    help = 'تشخيص الاتصال بـ Kafka'

    def handle(self, *args, **options):
        self.stdout.write("بدء تشخيص الاتصال بـ Kafka...")
        
        # التحقق من إعدادات Kafka
        kafka_bootstrap_servers = getattr(settings, 'KAFKA_BOOTSTRAP_SERVERS', '192.168.117.128:9094')
        kafka_success_topic = getattr(settings, 'KAFKA_SUCCESS_TOPIC', 'task-success')
        
        self.stdout.write(f"عنوان Kafka: {kafka_bootstrap_servers}")
        self.stdout.write(f"موضوع النجاح: {kafka_success_topic}")
        
        # محاولة الاتصال بـ Kafka
        self.stdout.write("\nمحاولة الاتصال بـ Kafka...")
        try:
            admin_client = admin.AdminClient({'bootstrap.servers': kafka_bootstrap_servers})
            
            # التحقق من الاتصال عن طريق طلب البيانات الوصفية للوسيط
            metadata = admin_client.list_topics(timeout=10)
            self.stdout.write(self.style.SUCCESS("تم الاتصال بـ Kafka بنجاح!"))
            
            # عرض معلومات الوسطاء
            self.stdout.write("\nمعلومات الوسطاء:")
            for broker in metadata.brokers.values():
                self.stdout.write(f"  - {broker.id}: {broker.host}:{broker.port}")
            
            # عرض المواضيع الموجودة
            self.stdout.write("\nالمواضيع الموجودة:")
            for topic, topic_metadata in metadata.topics.items():
                self.stdout.write(f"  - {topic}")
                
            # التحقق من وجود موضوع النجاح
            if kafka_success_topic in metadata.topics:
                self.stdout.write(self.style.SUCCESS(f"\nموضوع النجاح '{kafka_success_topic}' موجود!"))
            else:
                self.stdout.write(self.style.ERROR(f"\nموضوع النجاح '{kafka_success_topic}' غير موجود!"))
                
                # محاولة إنشاء الموضوع
                self.stdout.write("محاولة إنشاء الموضوع...")
                new_topics = [admin.NewTopic(
                    kafka_success_topic,
                    num_partitions=1,
                    replication_factor=1
                )]
                
                try:
                    admin_client.create_topics(new_topics)
                    self.stdout.write(self.style.SUCCESS("تم إنشاء الموضوع بنجاح!"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"فشل في إنشاء الموضوع: {e}"))
            
            # اختبار إرسال واستقبال رسالة
            self.stdout.write("\nاختبار إرسال واستقبال رسالة...")
            
            # إنشاء منتج
            producer = Producer({'bootstrap.servers': kafka_bootstrap_servers})
            
            # إنشاء رسالة اختبار
            test_message = {
                'test_id': str(uuid.uuid4()),
                'timestamp': time.time(),
                'message': 'هذه رسالة اختبار'
            }
            
            # إرسال الرسالة
            self.stdout.write("إرسال رسالة اختبار...")
            producer.produce(
                kafka_success_topic,
                json.dumps(test_message).encode('utf-8')
            )
            remaining = producer.flush(timeout=10)
            
            if remaining > 0:
                self.stdout.write(self.style.ERROR(f"لم يتم إرسال {remaining} رسائل خلال المهلة المحددة"))
            else:
                self.stdout.write(self.style.SUCCESS("تم إرسال الرسالة بنجاح!"))
            
            # إنشاء مستهلك
            self.stdout.write("\nمحاولة استقبال الرسالة...")
            consumer = Consumer({
                'bootstrap.servers': kafka_bootstrap_servers,
                'group.id': 'kafka-diagnostic-consumer',
                'auto.offset.reset': 'latest'
            })
            
            consumer.subscribe([kafka_success_topic])
            
            # محاولة استقبال الرسالة
            message_received = False
            start_time = time.time()
            timeout = 10  # ثواني
            
            while time.time() - start_time < timeout and not message_received:
                msg = consumer.poll(1.0)
                
                if msg is None:
                    self.stdout.write("انتظار الرسالة...")
                    continue
                
                if msg.error():
                    self.stdout.write(self.style.ERROR(f"خطأ في استقبال الرسالة: {msg.error()}"))
                else:
                    try:
                        received_data = json.loads(msg.value().decode('utf-8'))
                        self.stdout.write(self.style.SUCCESS("تم استقبال رسالة!"))
                        self.stdout.write(f"محتوى الرسالة: {received_data}")
                        message_received = True
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"خطأ في معالجة الرسالة: {e}"))
            
            consumer.close()
            
            if not message_received:
                self.stdout.write(self.style.WARNING("لم يتم استقبال أي رسالة خلال المهلة المحددة"))
            
        except KafkaException as ke:
            self.stdout.write(self.style.ERROR(f"خطأ Kafka: {ke}"))
        except socket.gaierror as se:
            self.stdout.write(self.style.ERROR(f"خطأ في حل العنوان: {se}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"خطأ غير متوقع: {e}"))
