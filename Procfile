web: python manage.py collectstatic --noinput && python manage.py migrate && gunicorn --bind 0.0.0.0:${PORT:-8000} saresp.wsgi:application
