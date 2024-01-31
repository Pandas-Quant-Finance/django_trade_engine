#!/bin/bash

echo remove database
rm *.sqlite3 || true

echo remove migrations
files=( "./trade_engine" )

for file in "${files[@]}"
do
  find $file -path "*/migrations/*.py"
  find $file -path "*/migrations/*.py" -not -name "__init__.py" -delete
  find $file -path "*/migrations/*.pyc"  -delete
done

echo migrate
python manage.py migrate
python manage.py makemigrations
python manage.py migrate

echo create super user
#python manage.py createsuperuser
echo "from django.contrib.auth.models import User; User.objects.create_superuser('admin', 'a@a.a', 'admin')" | python manage.py shell
