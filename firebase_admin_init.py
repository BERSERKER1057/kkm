import firebase_admin
from firebase_admin import credentials, auth

cred = credentials.Certificate("serviceAccountKey.json")  # Download from Firebase Console → Project Settings → Service Accounts → Generate new private key
firebase_admin.initialize_app(cred)
