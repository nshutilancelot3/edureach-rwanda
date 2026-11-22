# Deployment Guide for EduReach Rwanda

This guide shows how to deploy EduReach Rwanda to a public URL in minutes.

## Quickest Option: Railway (Recommended)

Railway is the easiest option—it deploys directly from GitHub with no configuration needed.

### Steps:

1. **Go to Railway**: https://railway.app/
2. **Sign in with GitHub** (or create an account)
3. **Click "Deploy on Railway"** or go to: https://railway.app/new?template=https://github.com/nshutilancelot3/edureach-rwanda
4. **Authorize the app** to access your GitHub account
5. **Click "Deploy Now"** 
6. **Wait 2-3 minutes** for deployment to complete
7. **Copy the public URL** from the Railway dashboard (it will be something like `https://edureach-*.railway.app`)

Your app is now live!

### Demo Access:
- **Student**: username `student`, password `1234`
- **Teacher**: username `teacher`, password `teach123`
- **Admin**: username `admin`, password `admin123`

---

## Alternative: Render

If Railway doesn't work, use Render:

1. Go to https://render.com
2. Sign in with GitHub
3. Click "New +" → "Web Service"
4. Connect your GitHub repo: `nshutilancelot3/edureach-rwanda`
5. Configure:
   - **Name**: `edureach-rwanda`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt && python seed.py`
   - **Start Command**: `waitress-serve --port=$PORT --host=0.0.0.0 --call 'edureach:create_app'`
6. Click "Create Web Service"
7. Wait for deployment (2-3 minutes)

Your public URL will appear in the Render dashboard.

---

## Alternative: PythonAnywhere

If you prefer PythonAnywhere:

1. Go to https://www.pythonanywhere.com
2. Create a free account
3. Add a new web app → Flask → Python 3.10
4. Configure the WSGI file to point to `edureach:create_app`
5. Upload your code via GitHub or manually
6. Reload the web app

Your URL will be `https://<username>.pythonanywhere.com`

---

## Verification After Deployment

Once deployed, verify everything works:

1. **Open the public URL** in your browser
2. **Login with** `student` / `1234`
3. **Open a lesson** to test offline content access
4. **Take a quiz** and verify auto-marking works
5. **Logout and login as teacher** (`teacher` / `teach123`) to verify teacher features

If all these work, your deployment is successful! 🎉

---

## Important Notes

- The app uses SQLite which resets on some deployment platforms. For persistent data, you may need to configure a managed database (ask the deployment platform for PostgreSQL or similar).
- Database and uploaded files are stored in `instance/` directory, which is not persistent on free-tier platforms. Consider this for pilots where data needs to survive between deployments.
- For a real deployment, change the demo passwords immediately.

---

## Support

If deployment fails:
- Check the deployment logs on Railway/Render/PythonAnywhere
- Ensure Python 3.9+ is available
- Verify `requirements.txt` is in the root directory
- Check that `Procfile` is correctly formatted
