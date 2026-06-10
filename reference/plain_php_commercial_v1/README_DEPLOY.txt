Web Automation Studio - PHP commercial backend

Target domain:
tools.haobanfa.online

Recommended stack:
- BaoTa panel
- Nginx
- PHP 8.1 or newer
- MySQL 5.7/8.0
- PHP extensions: pdo_mysql, curl, mbstring

1. Create MySQL database in BaoTa

Example:
database: webauto
username: webauto
password: your-db-password

Import:
database/schema.sql

2. Configure PHP app

Edit:
config/config.php

Required:
- db.database
- db.username
- db.password
- admin_password
- app_url

3. Upload files

Upload this folder to:
/www/wwwroot/tools.haobanfa.online

BaoTa website root must be:
/www/wwwroot/tools.haobanfa.online/public

Do not set the site root to the parent folder. The public folder is the only public web directory.

4. Disable old Python reverse proxy

If your current BaoTa site has a reverse proxy to 127.0.0.1:8088, disable it when switching to PHP.
PHP version does not need uvicorn, nohup, .venv, or port 8088.

5. Check installation

Open:
https://tools.haobanfa.online/install_check.php

After all checks are OK, delete install_check.php.

6. Public pages

/
/training.php
/console.php

Admin page:
/admin.php

The admin page is not linked from public pages. Use the admin_password in config/config.php.

7. Commercial features included

- User registration/login
- Free generation quota
- Paid generation quota
- Admin user management
- Manual paid order creation
- Quota logs
- Model API configuration
- Model connection test
- AI generation records
- Failure feedback logs
- Training playground

8. Desktop software API endpoints

POST /api.php?action=auth.login
GET  /api.php?action=me
POST /api.php?action=ai.generate
POST /api.php?action=feedback.create

Authorization:
Bearer user_token
