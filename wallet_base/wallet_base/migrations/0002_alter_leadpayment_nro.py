# Generated by Django 4.2.19 on 2024-05-19 11:28

import aesfield.field
from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("wallet_base", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="leadpayment",
            name="nro",
            field=aesfield.field.AESField(
                aes_key="", aes_method=settings.AES_METHOD, aes_prefix="aes:"
            ),
        ),
    ]
