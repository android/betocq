#!/system/bin/sh

# This script merely copies a file from the runfiles or temporary directory into
# the app's data directory.  Note that this script is just a template;
# ARG_APP_PACKAGE_NAME and ARG_HERMETIC_OVERRIDES_SOURCE_GOOGLE3 are
# substituted via a genrule.
# You can also use ARG_HERMETIC_OVERRIDES_SOURCE_DEVICE to set the path of
# overrides file. It is useful for the test running on Mobile Harness where the
# overrides file is pushed onto the testing device to a specific path
# (e.g. /data/local/tmp/) through MH decorator AndroidFilePusherDecorator.
# Note that once ARG_HERMETIC_OVERRIDES_SOURCE_DEVICE is set,
# ARG_HERMETIC_OVERRIDES_SOURCE_GOOGLE3 will be ignored.
# MERGE_EXISTING_OVERRIDES is to signal if there is an override file already
# then it is appended to contents of new override file content
APP_PACKAGE_NAME="${ARG_APP_PACKAGE_NAME}"
HERMETIC_OVERRIDES_SOURCE_GOOGLE3="${ARG_HERMETIC_OVERRIDES_SOURCE_GOOGLE3}"
MERGE_EXISTING_OVERRIDES="${ARG_MERGE_EXISTING_OVERRIDES}"
TAG="HermeticFileOverridesSetupScript"

function mylog() {
  # Go to both logcat and stderr (which shows up in waterfall).
  log -t "${TAG}" "$@"
  echo "$@" >&2
}

function fail() {
  mylog -p e "$@"
  # Reboot so that android_test notices the failure.
  reboot
  exit 1
}

function check_exists() {
  [[ -e "$1" ]] || fail "Cannot find $1"
}

DE_BASE="${ANDROID_DATA}/user_de"
DE_DATA="${DE_BASE}/0"
DATA_DIR="${ANDROID_DATA}/data"
DATA_DIRS="${DATA_DIR}"

if [[ -e "${DE_DATA}/${APP_PACKAGE_NAME}" ]]; then
  mylog "Using direct-boot data directory: ${DE_BASE}."
  # Do not quote so the glob will be expanded to include each UNIX user ID.
  DATA_DIRS=$DE_BASE/*
else
  mylog "Using non-direct-boot data directory: ${DATA_DIR}."
fi

for DATA_DIR in $DATA_DIRS; do
  # Dump directly to the data dir instead of files dir, because the files dir
  # might not yet exist, and there's no easy way in a fixture script to chown
  # the files dir to the app; the alternative, making it
  # world-readable-writeable, is pretty awful.
  APP_DATA_DIR="${DATA_DIR}/${APP_PACKAGE_NAME}"

  if [[ "${APP_DATA_DIR}" == *"/0/"* ]]; then
    # Enforce that the data dir must exist for user 0.
    check_exists "${APP_DATA_DIR}"
  else
    if [[ ! -e "${APP_DATA_DIR}" ]]; then
      mylog "WARNING ${APP_DATA_DIR} does not exist, flag overrides may not work for this user."
      continue
    fi
  fi

  FLAGS_DIR="${APP_DATA_DIR}/app_phenotype_hermetic"
  mkdir -p "${FLAGS_DIR}" || fail "Cannot create ${FLAGS_DIR}"
  # Properly chowning the data directory is basically impossible given the
  # minimal shell on old Android versions. Instead, we make it world-writeable;
  # at least, we are not making the entire files dir world writeable.
  chmod 777 "${FLAGS_DIR}" || fail "Cannot chmod ${FLAGS_DIR}"

  FLAGS_DESTINATION="${FLAGS_DIR}/overrides.txt"
  mylog "Target file is: ${FLAGS_DESTINATION}"

  if [[ "${ARG_HERMETIC_OVERRIDES_SOURCE_DEVICE}" != "" ]]; then
    HERMETIC_OVERRIDES_SOURCE_DEVICE="${ARG_HERMETIC_OVERRIDES_SOURCE_DEVICE}"
  else
    RUNFILES="${EXTERNAL_STORAGE}/googletest/test_runfiles"
    HERMETIC_OVERRIDES_SOURCE_DEVICE="${RUNFILES}/google3/${HERMETIC_OVERRIDES_SOURCE_GOOGLE3}"
  fi
  mylog "Source file is: ${HERMETIC_OVERRIDES_SOURCE_DEVICE}"
  check_exists "${HERMETIC_OVERRIDES_SOURCE_DEVICE}"

  # TODO(b/234062824) Merge override file at build time and avoid concatenation on device
  # Now, put our flags file in the right place!
  if [[ -e "${FLAGS_DESTINATION}" ]] && [[ "${MERGE_EXISTING_OVERRIDES}" = True ]]; then
    # if there is an override file the values in that should take precdence so
    # take a backup of the existing file and copy the launches on flags
    # and then append the contents of the backed up overrides files
    mylog "Override file exists already. Appending existing override file content to launches on flags"
    FLAGS_BACKUP_FILE="${FLAGS_DESTINATION}.bak"
    mv "${FLAGS_DESTINATION}" "${FLAGS_BACKUP_FILE}" || fail "Couldn't backup existing overrides file"
    cat "${HERMETIC_OVERRIDES_SOURCE_DEVICE}" > "${FLAGS_DESTINATION}" || fail "Couldn't copy file"
    cat "${FLAGS_BACKUP_FILE}" >> "${FLAGS_DESTINATION}" || fail "Couldn't append existing overrides files to new overrides file"
    rm "${FLAGS_BACKUP_FILE}" || fail "Couldn''t delete the backup overrides file"
  else
    mylog "Copying ${HERMETIC_OVERRIDES_SOURCE_DEVICE} -> ${FLAGS_DESTINATION}"
    # (cp does not exist on older emulators)
    cat "${HERMETIC_OVERRIDES_SOURCE_DEVICE}" >"${FLAGS_DESTINATION}" || fail "Couldn't copy file"
    if [[ "$FLAGS_DESTINATION" == *"/com.android.vending/"* ]]; then
      OVERRIDE_FLAG_PROTO_FILE="${HERMETIC_OVERRIDES_SOURCE_DEVICE/.txt/.pb}"
      OVERRIDE_FLAG_PROTO_DESTINATION="${FLAGS_DESTINATION/.txt/.pb}"
      mylog "Copying ${OVERRIDE_FLAG_PROTO_FILE} -> ${OVERRIDE_FLAG_PROTO_DESTINATION}"
      cat "${OVERRIDE_FLAG_PROTO_FILE}" >"${OVERRIDE_FLAG_PROTO_DESTINATION}" || fail "Couldn't copy file"
      chmod 644 "${OVERRIDE_FLAG_PROTO_DESTINATION}" || fail "Couldn't chmod file"
    fi
  fi
  chmod 644 "${FLAGS_DESTINATION}" || fail "Couldn't chmod file"
done

mylog "Done!"
