# web-hook/models.py
from django.db import models

# قائمة بجميع الدول الأعضاء في جامعة الدول العربية، مع إضافة خيار "أخرى"
COUNTRY_CHOICES = (
    ('DZ', 'Algeria'),
    ('BH', 'Bahrain'),
    ('KM', 'Comoros'),
    ('DJ', 'Djibouti'),
    ('EG', 'Egypt'),
    ('IQ', 'Iraq'),
    ('JO', 'Jordan'),
    ('KW', 'Kuwait'),
    ('LB', 'Lebanon'),
    ('LY', 'Libya'),
    ('MR', 'Mauritania'),
    ('MA', 'Morocco'),
    ('OM', 'Oman'),
    ('PS', 'Palestine'),
    ('QA', 'Qatar'),
    ('SA', 'Saudi Arabia'),
    ('SO', 'Somalia'),
    ('SD', 'Sudan'),
    ('SY', 'Syria'),
    ('TN', 'Tunisia'),
    ('AE', 'United Arab Emirates'),
    ('YE', 'Yemen'),
    ('US', 'United States'),
    ('GB', 'United Kingdom'),
    ('FR', 'France'),
    ('IT', 'Italy'),
    ('ES', 'Spain'),
    ('ID', 'Indonesia'),
    ('IR', 'Iran'),
    ('TR', 'Turkey'),
    ('OT', 'Other'),  # هذا الخيار الجديد للدول غير المدرجة
)

# هذا النموذج لتخزين معلومات العميل
class Client(models.Model):
    # Jabber ID (JID) وهو معرف فريد للعميل
    jid = models.CharField(max_length=255, unique=True)
    # اسم العميل
    name = models.CharField(max_length=255)
    # بلد العميل مع خيارات محددة
    country = models.CharField(max_length=2, choices=COUNTRY_CHOICES, default='SA')

    def __str__(self):
        return self.name

# هذا النموذج لتخزين سجل المحادثات
class Message(models.Model):
    # ربط الرسالة بالعميل الذي أرسلها
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    
    # أنواع الرسائل
    MESSAGE_TYPES = (
        ('text', 'Text'),
        ('image', 'Image'),
        ('voice', 'Voice Note'),
    )
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES, default='text')
    
    # محتوى الرسالة النصي (اختياري)
    content = models.TextField(blank=True, null=True)
    
    # حقل لتخزين رابط الصورة (اختياري)
    image_url = models.URLField(max_length=200, blank=True, null=True)
    
    # حقل لتخزين رابط الرسالة الصوتية (اختياري)
    voice_note_url = models.URLField(max_length=200, blank=True, null=True)
    
    # وقت إرسال الرسالة
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.message_type == 'text':
            return f"Message from {self.client.name}: {self.content[:50]}..."
        else:
            return f"Message from {self.client.name}: ({self.message_type.capitalize()} message)"

# هذا النموذج لتخزين ردود المساعد
class Response(models.Model):
    # ربط الرد بالرسالة التي يرد عليها
    message = models.OneToOneField(
        Message, 
        on_delete=models.CASCADE, 
        primary_key=True 
    )
    # محتوى الرد النصي
    content = models.TextField()
    # وقت إرسال الرد
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # الاعتماد على __str__ لنموذج Message لتجنب الأخطاء
        return f"Response to {self.message}" if self.message else "Response to a deleted message"

