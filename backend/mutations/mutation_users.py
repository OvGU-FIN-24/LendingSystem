from argon2 import PasswordHasher
from flask import session
import graphene
import os
from string import Template
import traceback
import uuid

from authorization_check import reject_message
from config import db, template_directory
from schema import User, UserModel
from sendMail import sendMail

##################################
# Mutations for Users            #
##################################
class create_user(graphene.Mutation):
    """
    Creates a new user with the given parameters.
    """

    class Arguments:
        # Required user arguments
        email       = graphene.String(required=True)
        last_name   = graphene.String(required=True)
        first_name  = graphene.String(required=True)
        password    = graphene.String(required=True)

        # Optional user arguments
        country         = graphene.String(required=False)
        city            = graphene.String(required=False)
        postcode        = graphene.Int(required=False)
        street          = graphene.String(required=False)
        house_number    = graphene.Int(required=False)
        phone_number    = graphene.Int(required=False)
        matricle_number = graphene.Int(required=False)

    user        = graphene.Field(lambda: User)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    def mutate(self, info, email, last_name, first_name, password, country=None, city=None, postcode=None, street=None, house_number=None, phone_number=None, matricle_number=None):
        # Check if email is a valid University email address
        # TODO: remove prhn.dynpv.net for production: only for development needed
        allowed_email_domains = ["ovgu.de", "prhn.dynpc.net"]
        if not any([email.endswith(domain) for domain in allowed_email_domains]):
            return create_user(ok=False, info_text="Nur E-Mail Adressen mit der Endung 'ovgu.de' sind erlaubt.", status_code=403)
        
        try:
            user_exists = UserModel.query.filter_by(email=email).first()
            if user_exists:
                return create_user(ok=False, info_text="Die angegebene E-Mail wird bereits verwendet.", status_code=409)
            else:
                ph = PasswordHasher()
                password_hashed = ph.hash(password)
                user = UserModel(first_name=first_name, last_name=last_name, email=email, password_hash=password_hashed)

                if country:
                    user.country = country
                if city:
                    user.city = city
                if postcode:
                    user.postcode = postcode
                if street:
                    user.street = street
                if house_number:
                    user.house_number = house_number

                if phone_number:
                    user.phone_number = phone_number
                if matricle_number:
                    user.matricle_number = matricle_number

                db.add(user)
                db.commit()
                return create_user(ok=True, info_text="Der Nutzer wurde erfolgreich angelegt.", user=user, status_code=200)
        except Exception as e:
            print(e)
            tb = traceback.format_exc()
            return create_user(ok=False, info_text="Fehler beim Erstellen des Nutzers. " + str(e) + "\n" + str(tb), status_code=500)


class update_user(graphene.Mutation):
    """
    Updates content of the user with the given user_id.
    """

    class Arguments:
        # Required user arguments
        user_id     = graphene.String(required=True)
        email       = graphene.String(required=False)
        last_name   = graphene.String(required=False)
        first_name  = graphene.String(required=False)
        password    = graphene.String(required=False)

        # Optional user arguments
        country         = graphene.String(required=False)
        city            = graphene.String(required=False)
        postcode        = graphene.Int(required=False)
        street          = graphene.String(required=False)
        house_number    = graphene.Int(required=False)
        phone_number    = graphene.Int(required=False)
        matricle_number = graphene.Int(required=False)

    user        = graphene.Field(lambda: User)
    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    def mutate(self, info, user_id, email=None, last_name=None, first_name=None, password=None, country=None, city=None, postcode=None, street=None, house_number=None, phone_number=None, matricle_number=None):
        # Check if user is authorised
        try:
            session_user_id = session['user_id']
        except:
            return update_user(ok=False, info_text="Keine valide session vorhanden", status_code=419)
        
        if not (session_user_id == user_id):
            return update_user(ok=False, info_text=reject_message, status_code=403)
        
        try:
            user = UserModel.query.filter(UserModel.user_id == user_id).first()

            if not user:
                return update_user(ok=False, info_text="User not found. Can only query by user_id.", status_code=404)
            if email:
                user.email = email
            if last_name:
                user.last_name = last_name
            if first_name:
                user.first_name = first_name
            if password:
                ph = PasswordHasher()
                user.password_hash = ph.hash(password)

            if country:
                user.country = country
            if city:
                user.city = city
            if postcode:
                user.postcode = postcode
            if street:
                user.street = street
            if house_number:
                user.house_number = house_number

            if phone_number:
                user.phone_number = phone_number
            if matricle_number:
                user.matricle_number = matricle_number

            db.commit()
            return update_user(ok=True, info_text="User updated successfully", user=user, status_code=200)

        except Exception as e:
            print(e)
            tb = traceback.format_exc()
            return update_user(ok=False, info_text="Error updating user: " + str(e) + "\n" + str(tb), status_code=500)


class delete_user(graphene.Mutation):
    """
    Deletes the user with the given user_id.
    """

    class Arguments:
        user_id = graphene.String(required=True)

    ok          = graphene.Boolean()
    info_text   = graphene.String()
    status_code = graphene.Int()

    @staticmethod
    def mutate(self, info, user_id):
        # Check if user is authorised
        try:
            session_user_id = session['user_id']
        except:
            return delete_user(ok=False, info_text="Keine valide session vorhanden", status_code=419)
        
        if not (session_user_id == user_id):
            return delete_user(ok=False, info_text=reject_message, status_code=403)
        


        user = UserModel.query.filter(UserModel.user_id == user_id).first()
        if user:
            db.delete(user)
            db.commit()
            return delete_user(ok=True, info_text="Nutzer erfolgreich entfernt.", status_code=200)
        else:
            return delete_user(ok=False, info_text="Nutzer konnte nicht entfernt werden.", status_code=404)
