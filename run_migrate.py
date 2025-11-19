#!/usr/bin/env python
import os
import django
import sys
from django.core.management import call_command

# -------------------------------
# Step 1: Set Django settings
# -------------------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "richdatabundle_project.settings")

# -------------------------------
# Step 2: Setup Django
# -------------------------------
try:
    django.setup()
except Exception as e:
    print("Error setting up Django:", e)
    sys.exit(1)

# -------------------------------
# Step 3: Run migrations
# -------------------------------
try:
    print("Applying migrations...")
    call_command("makemigrations", "core")  # Ensure your app is included
    call_command("migrate")
    print("Migrations applied successfully.")
except Exception as e:
    print("Error running migrations:", e)
    sys.exit(1)

# -------------------------------
# Step 4 (Optional): Check Profile table
# -------------------------------
from django.contrib.auth.models import User
from core.models import Profile

try:
    # Ensure all existing users have profiles
    for user in User.objects.all():
        Profile.objects.get_or_create(user=user)
    print("Profiles checked/created for all users.")
except Exception as e:
    print("Error creating missing profiles:", e)
    sys.exit(1)

print("Run_migrate completed successfully. Ready to start Gunicorn!")
