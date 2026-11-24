# Google Cloud Access
To use Google Cloud, from browser or command line, you need to authenticate. If you don't have access, please write Ben Notkin to get set up. For instructions on how to give someone access, see [Granting Access to Others](#granting-access-to-others).

<!-- Inside of a Docker container, you'll need to authenticate with a service account. (For browser and interactive command line, you can sign in using Google Cloud Platform's website.) _Task: write instructions for what to do with service account._ -->

The City Scan automation uses Google Cloud for:
- **Google Earth Engine (GEE)** — satellite imagery and geospatial analysis
- **Google Cloud Storage (GCS)** — private data buckets (`city-scan-global-data`, `city-scan-gcs-data`) 

** need to properly setup cloud buckets. 

--- 
### Local Setup

#### 1. Install gcloud CLI

Download and install from https://cloud.google.com/sdk/docs/install

Make sure to follow the installation until initialization with:

```
# gcloud auth login
gcloud init
```

#### 2. Authenticate

```
gcloud auth application-default login
```

This stores credentials locally. The automation picks this up automatically.
- **macOS/Linux**: `~/.config/gcloud/application_default_credentials.json`
- **Windows**: `%APPDATA%\gcloud\application_default_credentials.json`

#### 3. Set GEE project (optional)

Default project is `city-scan-gee-test`. Override with:
```bash
export GEE_PROJECT=your-project-id
```

#### 4. Verify

```bash
# Check GEE
python -c "import ee; ee.Initialize(); print('GEE OK')"

# Check GCS
gcloud storage ls gs://city-scan-global-public/ --limit=1
```

--- 
## Granting Access to Others

### Google Cloud Console

1. Go to [IAM & Admin](https://console.cloud.google.com/iam-admin/)
2. Click "Grant access"
3. Enter the user's gmail in "New principals"
4. Assign role: "Editor"
5. Click "Save"

The user then runs `gcloud auth login` and `gcloud auth application-default login` to authenticate locally.

<!-- ### Google Earth Engine

The user also needs GEE access at https://code.earthengine.google.com/ -->

---

## Cloud Run Deployment

> Coming soon


--- 

## Troubleshooting

- **GEE auth fails**: Run `gcloud auth application-default login` again
- **GCS 403/404**: Ensure the account has Storage Object Viewer role on the buckets
- **"GCS credentials not found"**: The automation looks for `~/.config/gcloud/application_default_credentials.json`

> [!WARNING]
> Never commit credentials or JSON key files to the repository.

---

<!--
OLD DOCS (kept for reference):

## Access to online interface (old)

To grant someone access to the Google Cloud Platform online interface you will need their gmail address. You will then add them as a user to the project in the Google Cloud Console. This will let them log in to the Google Cloud Platform.

1. Go to the Google Cloud [IAM & Admin page](https://console.cloud.google.com/iam-admin/). (IAM stands for Identity and Access Management.)
2. Click "Grant access"
3. Put the new user's gmail in the field marked "New principals"
4. Assign the new user a role in the field marked "Select a role". We should develop a clearer rubric of which roles to assign, but for now, use "Editor" (_Task: Figure out specific roles we need TK_)
5. Click "Save"

## Access to command line tools (old — service account JSON approach)

In most contexts, a person can use the above user account to authenticate the `gcloud` command line tools – they will simply run `gcloud auth login` and follow the prompts. However, some scenarios, such as running `gcloud` from within a Docker container, require a [service account](https://cloud.google.com/iam/docs/service-account-overview).

1. Go to Google Cloud Service Accounts page: [IAM & Admin > Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Click "Create Service Account"
3. Name and describe the service account; you can use the generated service account ID or create your own
4. Select the following permissions: 1) Cloud Run Service Agent, and 2) Storage Object Admin
5. Click "Done"
6. After creating the service account, click on it and go to the "Keys" tab
7. "Add Key", "Create new key", select "JSON" and "Create"
8. A service account key JSON file will be downloaded to your computer. Share this file with the person who needs access to the command line tools. Tell them to store the file in a folder called `frontend/.access/`. (_Task: confirm this is, ultimately, the right location TK_)

This JSON file can be used to authenticate `gcloud` without browser access.

> The service account key file is sensitive information. Do not share it publicly or commit it to a repository. It should be treated like a password.
--> 