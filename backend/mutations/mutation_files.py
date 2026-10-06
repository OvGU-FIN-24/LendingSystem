import graphene
from graphene_file_upload.scalars import Upload
import os
import time

from authz import (guarded, require_right, require_staff_anywhere, require_file_edit,
                   org_of_phys, org_of_group, InvalidInput, NotFound)
from config import db, pdf_directory, picture_directory
from models import userRights
from schema import File, FileModel, GroupModel, OrganizationModel, PhysicalObjectModel

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
    def mutate(root, info, file, phys_picture_id=None, phys_manual_id=None, organization_id=None, group_id=None, show_index=None):
        # authorise against every given target; without a target the file stays
        # unattached (upload first, attach later), which staff of any organisation may do
        targets = False
        for phys_id in (phys_picture_id, phys_manual_id):
            if phys_id:
                require_right(org_of_phys(phys_id), userRights.inventory_admin)
                targets = True
        if group_id:
            require_right(org_of_group(group_id), userRights.inventory_admin)
            targets = True
        if organization_id:
            require_right(organization_id, userRights.organization_admin)
            targets = True
        if not targets:
            require_staff_anywhere()

        extension = file.filename.split('.')[-1].lower()
        if extension in ['jpg', 'jpeg', 'png', 'svg']:
            file_type = 'picture'
        elif extension in ['pdf']:
            file_type = 'pdf'
        else:
            raise InvalidInput("File type not supported.")

        file_name = str(time.time()) + "_" + os.path.basename(file.filename).replace(" ", "_")
        if file_type == 'picture':
            # Prüfe Dateigröße
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            if file_size > (100 * 1024 * 1024): #100MB
                raise InvalidInput("Die Datei ist zu groß. Maximal erlaubt sind 100 MB.")
            file.save(os.path.join(picture_directory, file_name))
        else:
            file.save(os.path.join(pdf_directory, file_name))

        db_file = FileModel(path=file_name, file_type=file_type)
        if phys_picture_id:
            db.query(PhysicalObjectModel).get(phys_picture_id).pictures.append(db_file)
        if phys_manual_id:
            db.query(PhysicalObjectModel).get(phys_manual_id).manual.append(db_file)
        if group_id:
            db.query(GroupModel).get(group_id).pictures.append(db_file)
        if organization_id:
            organization = db.query(OrganizationModel).get(organization_id)
            organization.reset_user_agreement()
            organization.agb = [db_file]
        if show_index:
            db_file.show_index = show_index

        db.add(db_file)
        db.commit()
        return upload_file(ok=True, info_text="File uploaded successfully.", file=db_file, status_code=200)


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
