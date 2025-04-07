
# نستدعي الحاجات اللي بنحتاجها
from django.contrib import admin # عشان نضيف الرابط حق لوحة التحكم
from django.urls import path, include # path عشان نعرف كل رابط لوحده، و include عشان نضم ملف روابط ثاني

# هذي القائمة هي اللي فيها كل الروابط الرئيسية حق المشروع
urlpatterns = [
    # الرابط حق لوحة تحكم الأدمن اللي تجي مع جانغو
    # لما تطلب /admin/ بيوديك لهناك
    path("admin/", admin.site.urls),

    # هانا بنقول لجانغو: أي رابط يبدأ بـ /jobs/
    # روح دور على باقي الرابط في الملف حق الروابط حق تطبيق jobs
    # اللي هو بيكون موجود في jobs/urls.py
    path("jobs/", include("jobs.urls")),
]
