"""
Demo data for development (Harry Potter themed), loaded with
`python manage.py seed-demo`.

Idempotent: objects are matched by natural keys (organisation/tag/group name,
user email, item name per organisation, order borrower + item), so running it
again adds nothing new. Existing passwords are never changed. Pictures are left
empty (the frontend shows the placeholder); each organisation gets a generated
AGB PDF.
"""
import json
import os
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from sqlalchemy import func

from config import application_root_user_name, db, pdf_directory
from models import (File, Group, Order, Organization, Organization_User,
                    PhysicalObject, PhysicalObject_Order, Tag, User,
                    orderStatus, userRights)

# Published on purpose: development demo data only, see backend/readme.md
DEMO_PASSWORD = "Alohomora-2026"  # NOSONAR
ROOT_ORGANIZATION = "root_organization"

GRYFFINDOR = "Hogwarts – Gryffindor"
SLYTHERIN = "Hogwarts – Slytherin"
MINISTRY = "Ministry of Magic"

ORGANIZATIONS = {
    GRYFFINDOR: ("Hogwarts, Gryffindor-Turm",
                 "Ausleihbedingungen des Hauses Gryffindor"),
    SLYTHERIN: ("Hogwarts, Kerker",
                "Ausleihbedingungen des Hauses Slytherin"),
    MINISTRY: ("London, Whitehall",
               "Ausleihbedingungen des Zaubereiministeriums"),
}

# Max deposit (cents) per right; staff rights are not capped further
MAX_DEPOSIT = {"customer": 5000, "member": 10000, "inventory_admin": 20000,
               "organization_admin": 20000, "system_admin": 20000}

HARRY = "harry.potter@ovgu.de"
HERMIONE = "hermione.granger@ovgu.de"
RON = "ron.weasley@ovgu.de"
DRACO = "draco.malfoy@ovgu.de"

_SA = userRights.system_admin
_OA = userRights.organization_admin
_IA = userRights.inventory_admin
_MEMBER = userRights.member
_CUSTOMER = userRights.customer

# email: (first name, last name, [(organisation, right)])
USERS = {
    "albus.dumbledore@ovgu.de": ("Albus", "Dumbledore",
                                 [(ROOT_ORGANIZATION, _SA)]),
    "minerva.mcgonagall@ovgu.de": ("Minerva", "McGonagall",
                                   [(GRYFFINDOR, _OA)]),
    "severus.snape@ovgu.de": ("Severus", "Snape", [(SLYTHERIN, _OA)]),
    "kingsley.shacklebolt@ovgu.de": ("Kingsley", "Shacklebolt",
                                     [(MINISTRY, _OA)]),
    "argus.filch@ovgu.de": ("Argus", "Filch",
                            [(GRYFFINDOR, _IA), (SLYTHERIN, _IA)]),
    HARRY: ("Harry", "Potter", [(GRYFFINDOR, _MEMBER)]),
    HERMIONE: ("Hermione", "Granger", [(GRYFFINDOR, _MEMBER),
                                       (SLYTHERIN, _CUSTOMER),
                                       (MINISTRY, _CUSTOMER)]),
    RON: ("Ron", "Weasley", [(GRYFFINDOR, _CUSTOMER)]),
    DRACO: ("Draco", "Malfoy", [(GRYFFINDOR, userRights.watcher),
                                (SLYTHERIN, _MEMBER)]),
}

NIMBUS = "Nimbus 2000"
CAULDRON_1 = "Cauldron No. 1"
CAULDRON_2 = "Cauldron No. 2"
ARTEFACTS = "Magische Artefakte"
POTIONS = "Zaubertränke"
SMALL_CAULDRON = "Zinnkessel, Größe 2."

# name: (organisation, deposit in cents, storage location, tags, description)
ITEMS = {
    NIMBUS: (GRYFFINDOR, 5000, "Besenschrank", ["Besen", "Quidditch"],
             "Rennbesen, sehr wendig."),
    "Firebolt": (GRYFFINDOR, 8000, "Besenschrank", ["Besen", "Quidditch"],
                 "Internationaler Standardbesen für Turniere."),
    "Invisibility Cloak": (GRYFFINDOR, 10000, "Schlafsaal, Truhe",
                           [ARTEFACTS],
                           "Tarnumhang, macht den Träger unsichtbar."),
    "Marauder's Map": (GRYFFINDOR, 3000, "Gemeinschaftsraum",
                       ["Karten", ARTEFACTS],
                       "Zeigt das Schloss und alle, die sich darin bewegen."),
    "Remembrall": (GRYFFINDOR, 1000, "Gemeinschaftsraum", [ARTEFACTS],
                   "Färbt sich rot, wenn man etwas vergessen hat."),
    "Sorting Hat": (GRYFFINDOR, 2000, "Büro der Schulleitung", [ARTEFACTS],
                    "Teilt neue Schülerinnen und Schüler den Häusern zu."),
    CAULDRON_1: (SLYTHERIN, 1500, "Kerker, Regal 1", [POTIONS],
                 SMALL_CAULDRON),
    CAULDRON_2: (SLYTHERIN, 1500, "Kerker, Regal 1", [POTIONS],
                 SMALL_CAULDRON),
    "Cauldron No. 3": (SLYTHERIN, 1500, "Kerker, Regal 2", [POTIONS],
                       "Messingkessel, Größe 3."),
    "Time-Turner": (MINISTRY, 15000, "Mysteriumsabteilung", [ARTEFACTS],
                    "Zeitumkehrer; nur mit Genehmigung."),
    "Pensieve": (MINISTRY, 12000, "Mysteriumsabteilung", [ARTEFACTS],
                 "Denkarium zum Betrachten von Erinnerungen."),
}

# name: (organisation, items, tags, description)
GROUPS = {
    "Quidditch-Set": (GRYFFINDOR, [NIMBUS, "Firebolt"], ["Quidditch"],
                      "Zwei Besen für das Training."),
    "Zaubertrank-Ausrüstung": (SLYTHERIN,
                               [CAULDRON_1, CAULDRON_2, "Cauldron No. 3"],
                               [POTIONS], "Drei Kessel für den Unterricht."),
}

# (borrower, item, status, start offset in days, length in days);
# dates are relative to the seeding day
ORDERS = [
    (HARRY, "Firebolt", orderStatus.picked, -3, 7),
    (HERMIONE, CAULDRON_1, orderStatus.picked, -1, 4),
    (HERMIONE, "Time-Turner", orderStatus.accepted, 5, 5),
    (RON, NIMBUS, orderStatus.pending, 2, 4),
    (HARRY, "Invisibility Cloak", orderStatus.returned, -20, 5),
    (RON, "Remembrall", orderStatus.rejected, 3, 2),
    (DRACO, CAULDRON_2, orderStatus.accepted, 1, 3),
]


def foreign_users():
    """Number of users that are neither the bootstrap root nor demo users."""
    known = {email.lower() for email in USERS}
    known.add((application_root_user_name or "").strip().lower())
    return db.query(User).filter(
        func.lower(User.email).notin_(known)).count()


def _pdf(title, lines):
    """Minimal one-page PDF (Helvetica, WinAnsi) with a title and text
    lines."""
    def esc(text):
        return (text.replace("\\", "\\\\").replace("(", "\\(")
                .replace(")", "\\)"))
    content = ["BT", "/F1 16 Tf", "50 790 Td", f"({esc(title)}) Tj",
               "/F1 11 Tf", "0 -30 Td"]
    for line in lines:
        content += [f"({esc(line)}) Tj", "0 -16 Td"]
    content.append("ET")
    stream = "\n".join(content).encode("cp1252")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, xref))
    return bytes(out)


def _agb_lines(org_name):
    return [
        f"Diese Bedingungen gelten für Ausleihen bei {org_name}.",
        "1. Ausgeliehene Gegenstände sind pfleglich zu behandeln.",
        "2. Die Rückgabe erfolgt spätestens am vereinbarten Tag.",
        "3. Schäden und Verluste werden mit der Kaution verrechnet.",
        "4. Verbotene Zauber an Leihgegenständen sind untersagt.",
        "Dies sind Demo-Daten für die Entwicklung.",
    ]


def _get_or_create(model, created=None, kind=None, defaults=None, **keys):
    """Returns the row matching keys, creating it with defaults if missing
    (counted in created[kind])."""
    obj = db.query(model).filter_by(**keys).first()
    if obj is None:
        obj = model(**keys, **(defaults or {}))
        db.add(obj)
        db.flush()
        if created is not None:
            created[kind] = created.get(kind, 0) + 1
    return obj


def _ensure_agb(org, slug, title):
    file_name = f"demo_agb_{slug}.pdf"
    os.makedirs(pdf_directory, exist_ok=True)
    path = os.path.join(pdf_directory, file_name)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(_pdf(title, _agb_lines(org.name)))
    if not org.agb:
        org.agb = [_get_or_create(File, path=file_name,
                                  defaults={"file_type": File.FileType.pdf})]


def _ensure_membership(org, user, right):
    membership = db.query(Organization_User).filter_by(
        organization_id=org.organization_id, user_id=user.user_id).first()
    if membership is None:
        db.add(Organization_User(organization_id=org.organization_id,
                                 user_id=user.user_id, rights=right))
    else:
        membership.rights = right


def _add_missing(collection, objects):
    for obj in objects:
        if obj not in collection:
            collection.append(obj)


def _day(offset):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return today + timedelta(days=offset)


def _seed_organizations(created):
    orgs = {ROOT_ORGANIZATION: _get_or_create(
        Organization, created, "organizations", name=ROOT_ORGANIZATION,
        defaults={"location": "application"})}
    for slug, (name, (location, agb_title)) in enumerate(
            ORGANIZATIONS.items(), start=1):
        org = _get_or_create(Organization, created, "organizations",
                             name=name, defaults={"location": location})
        org.max_deposit = json.dumps(MAX_DEPOSIT)
        _ensure_agb(org, slug, agb_title)
        orgs[name] = org
    return orgs


def _seed_users(created, orgs):
    hasher = PasswordHasher()
    users = {}
    for email, (first, last, memberships) in USERS.items():
        user = db.query(User).filter_by(email=email).first()
        if user is None:
            user = _get_or_create(User, created, "users", email=email,
                                  defaults={"first_name": first,
                                            "last_name": last,
                                            "password_hash":
                                                hasher.hash(DEMO_PASSWORD)})
        for org_name, right in memberships:
            _ensure_membership(orgs[org_name], user, right)
        users[email] = user
    return users


def _seed_tags(created):
    names = ({t for item in ITEMS.values() for t in item[3]}
             | {t for group in GROUPS.values() for t in group[2]})
    return {name: _get_or_create(Tag, created, "tags", name=name)
            for name in sorted(names)}


def _seed_items(created, orgs, tags):
    items = {}
    for number, (name, item) in enumerate(ITEMS.items(), start=1):
        org_name, deposit, location, tag_names, description = item
        obj = _get_or_create(
            PhysicalObject, created, "items", name=name,
            organization_id=orgs[org_name].organization_id,
            defaults={"inv_num_internal": 9000 + number,
                      "inv_num_external": 4000 + number,
                      "deposit": deposit, "storage_location": location,
                      "description": description, "faults": "",
                      "borrowable": True})
        _add_missing(obj.tags, [tags[t] for t in tag_names])
        items[name] = obj
    return items


def _seed_groups(created, orgs, tags, items):
    for name, (org_name, item_names, tag_names, description) in GROUPS.items():
        group = _get_or_create(
            Group, created, "groups", name=name,
            defaults={"organization_id": orgs[org_name].organization_id,
                      "description": description})
        _add_missing(group.physicalobjects, [items[i] for i in item_names])
        _add_missing(group.tags, [tags[t] for t in tag_names])


def _seed_orders(created, users, items):
    for email, item_name, status, start, length in ORDERS:
        user, item = users[email], items[item_name]
        exists = (db.query(Order).join(PhysicalObject_Order)
                  .filter(Order.users.any(User.user_id == user.user_id),
                          PhysicalObject_Order.phys_id == item.phys_id)
                  .first())
        if exists:
            continue
        org = item.organization
        right = db.query(Organization_User.rights).filter_by(
            organization_id=org.organization_id,
            user_id=user.user_id).scalar() or userRights.customer
        end = _day(start + length)
        order = Order(creation_date=datetime.now(), from_date=_day(start),
                      till_date=end, organization_id=org.organization_id,
                      deposit=min(item.deposit, org.get_max_deposit(right)))
        order.users.append(user)
        order.physicalobjects.append(PhysicalObject_Order(
            physicalobject=item, order_status=status,
            return_date=end if status == orderStatus.returned else None))
        db.add(order)
        created["orders"] = created.get("orders", 0) + 1


def seed():
    """Loads the demo data; returns a dict with the number of objects
    created per kind."""
    created = {}
    orgs = _seed_organizations(created)
    users = _seed_users(created, orgs)
    tags = _seed_tags(created)
    items = _seed_items(created, orgs, tags)
    _seed_groups(created, orgs, tags, items)
    db.flush()
    _seed_orders(created, users, items)
    db.commit()
    return created
