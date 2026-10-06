import graphene
from graphene_file_upload.scalars import Upload
import os
import time

from authz import (guarded, require_right, require_staff_anywhere,
                   require_file_edit,
                   org_of_phys, org_of_group, InvalidInput, NotFound)
from config import db, pdf_directory, picture_directory
from models import userRights
from schema import File, FileModel, OrganizationModel

##################################
# Upload for Files               #
##################################
class upload_file(graphene.Mutation):
    """
    Uploads a file to the server and creates a new File object in the database.
    """

    class Arguments:
        phys_picture_id     = graphene.String()
        phys_manual_id      = graphene.String()
        organization_id     = graphene.String()
        group_id            = graphene.String()
        show_index          = graphene.Int()
        file                = Upload(required=True)

    file        = graphene.Field(lambda: File)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, file, **targets):
        _authorize_upload(**targets)
        file_type = _file_type(file.filename)
        file_name = _store(file, file_type)

        # set the foreign keys directly; no detached parent object is needed
        db_file = FileModel(
            path=file_name,
            file_type=file_type,
            picture_id=targets.get("phys_picture_id"),
            manual_id=targets.get("phys_manual_id"),
            group_id=targets.get("group_id"),
            show_index=targets.get("show_index") or None,
        )
        organization_id = targets.get("organization_id")
        if organization_id:
            organization = db.query(OrganizationModel).get(organization_id)
            organization.reset_user_agreement()
            organization.agb = [db_file]

        db.add(db_file)
        db.commit()
        return upload_file(ok=True, info_text="File uploaded successfully.",
                           file=db_file, status_code=200)


def _authorize_upload(phys_picture_id=None, phys_manual_id=None,
                      organization_id=None, group_id=None, show_index=None):
    """
    Authorise against every given target. Without a target the file stays
    unattached (upload first, attach later), which staff of any organisation
    may do.
    """
    checks = [(org_of_phys(p), userRights.inventory_admin)
              for p in (phys_picture_id, phys_manual_id) if p]
    if group_id:
        checks.append((org_of_group(group_id), userRights.inventory_admin))
    if organization_id:
        checks.append((organization_id, userRights.organization_admin))
    if not checks:
        require_staff_anywhere()
    for org_id, right in checks:
        require_right(org_id, right)


def _file_type(filename):
    extension = filename.split('.')[-1].lower()
    if extension in ['jpg', 'jpeg', 'png', 'svg']:
        return 'picture'
    if extension in ['pdf']:
        return 'pdf'
    raise InvalidInput("File type not supported.")


def _store(file, file_type):
    base_name = os.path.basename(file.filename).replace(" ", "_")
    file_name = str(time.time()) + "_" + base_name
    if file_type == 'picture':
        # Prüfe Dateigröße
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > (100 * 1024 * 1024):  # 100MB
            raise InvalidInput(
                "Die Datei ist zu groß. Maximal erlaubt sind 100 MB.")
        file.save(os.path.join(picture_directory, file_name))
    else:
        file.save(os.path.join(pdf_directory, file_name))
    return file_name


class update_file(graphene.Mutation):
    """
    Updates the file with the given file_id.
    """

    class Arguments:
        file_id     = graphene.String(required=True)

        show_index  = graphene.Int()

    file        = graphene.Field(lambda: File)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()
    upload_file = graphene.Int(description="Deprecated: same value as statusCode")

    @staticmethod
    def mutate(root, info, file_id, show_index=None):
        result = update_file._mutate(root, info, file_id=file_id, show_index=show_index)
        result.upload_file = result.status_code
        return result

    @staticmethod
    @guarded
    def _mutate(root, info, file_id, show_index=None):
        db_file = db.query(FileModel).get(file_id)
        if not db_file:
            require_staff_anywhere()
            raise NotFound("File not found.")
        require_file_edit(db_file)

        if show_index:
            db_file.show_index = show_index

        db.commit()
        return update_file(ok=True, info_text="File updated successfully.", file=db_file, status_code=200)


class delete_file(graphene.Mutation):
    """
    Deletes the file with the given file_id from the server and the database.
    """

    class Arguments:
        file_id = graphene.String(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    @guarded
    def mutate(root, info, file_id):
        db_file = db.query(FileModel).get(file_id)
        if not db_file:
            require_staff_anywhere()
            raise NotFound("File not found.")
        require_file_edit(db_file)

        directory = picture_directory if db_file.file_type == FileModel.FileType.picture else pdf_directory
        path = os.path.join(directory, os.path.basename(db_file.path))

        db.delete(db_file)
        db.commit()
        if os.path.isfile(path):
            os.remove(path)
        return delete_file(ok=True, info_text="File successfully removed.", status_code=200)
