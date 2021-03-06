# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-10-16 20:22
from __future__ import unicode_literals

from django.db import migrations

OLD_NAME = 'AsPredicted Preregistration'
NEW_NAME = 'Preregistration Template from AsPredicted.org'

def rename_schema(model, from_name, to_name):
    try:
        schema = model.objects.get(name=from_name)
    except model.DoesNotExist:
        return

    schema.name = to_name
    schema.schema['name'] = to_name
    schema.schema['title'] = to_name
    schema.schema['pages'][0]['title'] = to_name
    return schema.save()

def rename_aspredicted_schema(state, schema):
    RegistrationSchema = state.get_model('osf.registrationschema')
    return rename_schema(RegistrationSchema, OLD_NAME, NEW_NAME)

def undo_aspredicted_rename(state, schema):
    RegistrationSchema = state.get_model('osf.registrationschema')
    return rename_schema(RegistrationSchema, NEW_NAME, OLD_NAME)

class Migration(migrations.Migration):

    dependencies = [
        ('osf', '0138_merge_20181012_1944'),
    ]

    operations = [
        migrations.RunPython(rename_aspredicted_schema, undo_aspredicted_rename)
    ]
