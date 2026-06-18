def upload_blob(bucket_name, source_file_name, destination_blob_name, type = 'output', check_exists = False):
    """
    Uploads a file to the bucket.

    Args:
        bucket_name: Name of the bucket.
        source_file_name: Path to the file to upload.
        destination_blob_name: Destination name of the file in the bucket.
        type: Type of the file (output (default), render, input, data)
        check_exists: Check if the file already exists in the bucket.
    """
    import os
    from google.cloud import storage
    from os.path import exists

    if exists(source_file_name):
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)

        if type == 'output':
            # Mapping of file extensions to folder names
            folder_map = {
                ('.tif', '.gpkg'): 'spatial',
                ('.csv', '.txt', '.yml'): 'tabular',
                ('.png'): 'images'
            }

            # Default folder name for other file types
            default_folder = 'other'

            # Get the folder name based on file extension
            for extensions, folder_name in folder_map.items():
                if any(destination_blob_name.endswith(ext) for ext in extensions):
                    target_folder = folder_name
                    break
            else:
                target_folder = default_folder

            # Construct the new destination_blob_name
            destination_blob_name = f'{os.path.dirname(destination_blob_name)}/{target_folder}/{os.path.basename(destination_blob_name)}'
        elif type == 'render':
            # Mapping of file extensions to folder names
            folder_map = {
                ('.html'): 'plots/html',
                ('.png'): 'plots/png'
            }

            # Default folder name for other file types
            default_folder = 'other'

            # Get the folder name based on file extension
            for extensions, folder_name in folder_map.items():
                if any(destination_blob_name.endswith(ext) for ext in extensions):
                    target_folder = folder_name
                    break
            else:
                target_folder = default_folder

            # Construct the new destination_blob_name
            destination_blob_name = f'{os.path.dirname(destination_blob_name)}/{target_folder}/{os.path.basename(destination_blob_name)}'

        blob = bucket.blob(destination_blob_name)
        if check_exists:
            if blob.exists():
                print(f"File {destination_blob_name} already exists.")
                return
        blob.upload_from_filename(source_file_name)
        print(f"File {source_file_name} uploaded to {destination_blob_name}.")
        return True
    print(f"File {source_file_name} does not exist.")
    return False


def get_all_files(directory):
    """
    Get set of all files in a directory tree.
    Returns absolute paths of all files found.
    """
    import os
    
    if not os.path.exists(directory):
        return set()
    
    files = set()
    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            files.add(os.path.join(root, filename))
    return files


def upload_inputs(scan):
    """
    Upload 01-user-input to GCS (city_inputs.yml, menu.yml, AOI/, wards/, ...).

    Inputs are static for a run, so this is called once per upload-enabled run
    rather than on the per-task diff. GCS-based runs read a city's inputs from
    here instead of the parent inputs/ folder.

    Uploads to: cityscan_id/01-user-input/...
    """
    from google.cloud import storage
    import os
    from core.py.log_module import setup_logger

    logger = setup_logger("gcs_upload")

    try:
        bucket_name = "crp-city-scan"
        bucket = storage.Client().bucket(bucket_name)

        input_files = get_all_files(scan.input_dir)
        if not input_files:
            return True

        uploaded_count = 0
        for local_path in input_files:
            try:
                relative_path = os.path.relpath(local_path, os.path.dirname(scan.input_dir))
                gcs_path = f"{scan.cityscan_id}/{relative_path}"
                bucket.blob(gcs_path).upload_from_filename(local_path)
                logger.info(f"Uploaded: gs://{bucket_name}/{gcs_path}")
                uploaded_count += 1
            except Exception as e:
                logger.error(f"Failed to upload {local_path}: {e}")
                continue

        logger.info(f"Inputs: Uploaded {uploaded_count} files to gs://{bucket_name}/{scan.cityscan_id}/01-user-input/")
        return True

    except Exception as e:
        logger.error(f"Critical error uploading inputs: {e}")
        return False


def download_scan_folder(scan_id, folder, overwrite=None):
    """
    Download a scan's folder from GCS to local mnt/ (pull; symmetric to upload).

    Downloads gs://crp-city-scan/{scan_id}/{name}/... to OUTPUTS/{scan_id}/{name}/...

    Args:
        scan_id: Scan folder name (e.g. '2026-04-namibia-windhoek').
        folder: '01', '02', or '03' (→ 01-user-input / 02-process-output /
                03-render-output).
        overwrite: True  = always re-download
                   False = skip if local folder already has files
                   None  = ask (interactive); keep if non-interactive

    Returns:
        int: number of files downloaded
    """
    from google.cloud import storage
    import os
    import sys
    from pathlib import Path
    from core.config.paths import OUTPUTS
    from core.py.log_module import setup_logger

    logger = setup_logger("gcs_download")

    folder_map = {"01": "01-user-input", "02": "02-process-output", "03": "03-render-output"}
    name = folder_map.get(folder)
    if name is None:
        logger.error(f"Unknown download folder '{folder}' (use 01, 02, or 03)")
        return 0

    local_root = Path(OUTPUTS) / scan_id / name

    # Decide whether to download when a local copy already exists
    if local_root.exists() and any(local_root.rglob("*")):
        if overwrite is None:
            if sys.stdin.isatty():
                resp = input(f"  {name} already exists locally — overwrite from GCS? (y/n) ").strip().lower()
                if resp != "y":
                    logger.info(f"Keeping local {name}")
                    return 0
            else:
                logger.info(f"Keeping local {name} (non-interactive)")
                return 0
        elif overwrite is False:
            return 0

    try:
        bucket_name = "crp-city-scan"
        bucket = storage.Client().bucket(bucket_name)
        prefix = f"{scan_id}/{name}/"
        blobs = [b for b in bucket.list_blobs(prefix=prefix) if not b.name.endswith("/")]
        if not blobs:
            logger.warning(f"No files in gs://{bucket_name}/{prefix}")
            return 0

        count = 0
        for blob in blobs:
            # blob.name is '{scan_id}/{name}/...'; mirror it under OUTPUTS
            local_path = Path(OUTPUTS) / blob.name
            local_path.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(local_path))
            count += 1

        logger.info(f"Downloaded {count} files from gs://{bucket_name}/{prefix} to {local_root}")
        return count

    except Exception as e:
        logger.error(f"Critical error downloading {name} for {scan_id}: {e}")
        return 0


def upload_task_outputs(scan, task_name, step=None, files_before=None):
    """
    Upload task outputs to GCS. Only uploads files that didn't exist before.
    
    Automatically constructs paths using scan.cityscan_id and scan.output_dir/render_dir.
    Example: local file 'mnt/2026-03-indonesia-south_jakarta/02-process-output/spatial/file.tif'
             uploads to 'gs://crp-city-scan/2026-03-indonesia-south_jakarta/02-process-output/spatial/file.tif'
    
    Args:
        scan: Scan object with cityscan_id and output directories
        task_name: Name of the task (e.g., 'wsf', 'accessibility')
        step: Optional step identifier ('collect', 'analyze', 'visualize', or None for full run)
        files_before: Set of files that existed before task execution.
                     If None, uploads all current files.
    
    Returns:
        bool: True if upload succeeded or was fully attempted, False on critical error
    """
    from google.cloud import storage
    import os
    from core.py.log_module import setup_logger
    
    logger = setup_logger("gcs_upload")
    
    try:
        bucket_name = "crp-city-scan"
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        
        # Get current files (task outputs only; 01-user-input is uploaded once
        # per run via upload_inputs, not on the per-task diff)
        current_files = get_all_files(scan.output_dir) | get_all_files(scan.render_dir)
        
        # Determine new files
        if files_before is not None:
            new_files = current_files - files_before
        else:
            new_files = current_files
        
        if not new_files:
            step_str = f" ({step})" if step else ""
            logger.info(f"Task '{task_name}'{step_str}: No new files to upload")
            return True
        
        # Upload each new file
        uploaded_count = 0
        for local_path in new_files:
            try:
                # Determine relative path from parent of output_dir
                if local_path.startswith(str(scan.output_dir)):
                    relative_path = os.path.relpath(local_path, os.path.dirname(scan.output_dir))
                elif local_path.startswith(str(scan.render_dir)):
                    relative_path = os.path.relpath(local_path, os.path.dirname(scan.render_dir))
                else:
                    logger.warning(f"File {local_path} not in expected directories, skipping")
                    continue
                
                # Construct GCS path: cityscan_id/02-process-output/...
                gcs_path = f"{scan.cityscan_id}/{relative_path}"
                
                # Upload to GCS
                blob = bucket.blob(gcs_path)
                blob.upload_from_filename(local_path)
                logger.info(f"Uploaded: gs://{bucket_name}/{gcs_path}")
                uploaded_count += 1
                
            except Exception as e:
                logger.error(f"Failed to upload {local_path}: {e}")
                continue
        
        step_str = f" ({step})" if step else ""
        logger.info(f"Task '{task_name}'{step_str}: Uploaded {uploaded_count} files to gs://{bucket_name}/{scan.cityscan_id}/")
        return True
        
    except Exception as e:
        logger.error(f"Critical error uploading outputs for task '{task_name}': {e}")
        return False