import React, { startTransition, useState } from "react";
import { useLoginStatus } from "../../context/LoginStatusContext";
import { FaUserEdit, FaTrash } from "react-icons/fa";
import { Login } from "../login/Login";
import { gql } from "@apollo/client"; 
import { OrganizationInfo } from "../../models/user.model";
import { useLazyQuery } from "@apollo/client";
import { useMutation } from "@apollo/client";
import { useGetUserIDbyEmail } from "../../hooks/user-helper";
import { useGetOrganizationByIdQuery } from "../../hooks/organization-helper";
import { useSuspenseQueryWithResponseMapped } from "../../hooks/response-helper";

import "./Profile.css";

const GET_USERS = gql`
query getUsersByOrganization($organizationIds: [String!]){
  filterUsers (organizations: $organizationIds) {
    firstName
    lastName
    email
    userId
    organizations{
      edges {
        node
        {
         organizationId 
         rights
         }
      }
    }
  }
}`;

const UPDATE_USER_RIGHTS = gql`
  mutation updateUserRights($newRights: String!, $organizationId: String!, $userId: String!) {
    updateUserRights(newRights: $newRights, organizationId: $organizationId, userId: $userId) {
      ok
      infoText
      statusCode
    }
  }
`;

const REMOVE_USER_FROM_ORG = gql`
  mutation removeUserFromOrganization($organizationId: String!, $userId: String!) {
    removeUserFromOrganization(organizationId: $organizationId, userId: $userId) {
      ok
      infoText
      statusCode
    }
  }
`;

const CREATE_ORGANIZATION = gql`
  mutation createOrganization($agb: String, $location: String!, $name: String!, $physicalobjects: [String], $users: [String]) {
    createOrganization(agb: $agb, location: $location, name: $name, physicalobjects: $physicalobjects, users: $users, ) {
      ok
      infoText
      statusCode
    }
  }
`;

export function GetOrgName(orgId: string){
  return useGetOrganizationByIdQuery(orgId);
}

export const GetHighestUserRights = () => {
  const loginStatus = useLoginStatus();
  if (!loginStatus.loggedIn){
    return "";
  }

  if (!loginStatus?.user?.organizationInfoList?.length) {
    return "";
  }

  const rightsHierarchy = ["WATCHER", "CUSTOMER", "MEMBER", "ORGANIZATION_ADMIN", "SYSTEM_ADMIN"];

  // Get all user rights from organizations
  // @ts-ignore
  const userRights = loginStatus.user.organizationInfoList
  .map((org: OrganizationInfo) => org.rights) // Explicitly type org
  .filter(Boolean);

  if (userRights.length === 0) {
    return ""; // No valid rights found
  }
  // @ts-ignore
  // Find the highest rights based on hierarchy
  return userRights.reduce((highest, current) => 
    rightsHierarchy.indexOf(current) > rightsHierarchy.indexOf(highest) ? current : highest
  );
};



export function OrganizationManagement() {
  const loginStatus = useLoginStatus();
  const [selectedOrganizationId, setSelectedOrganizationId] = useState<string>("nichts");  
  const [searchTerm, setSearchTerm] = useState("");
  const [isRoleModalOpen, setRoleModalOpen] = useState(false);
  const [isUserDeleteOpen, setUserDeleteOpen] = useState(false);
  const [isOrganizationModalOpen, setOrganizationModalOpen] = useState(false);
  const [roleEmail, setRoleEmail] = useState("");
  const [orgName, setOrgName] = useState("");
  const [selectedRole, setSelectedRole] = useState("member");
  const highestUserRights = GetHighestUserRights();
  const [errorMessage, setErrorMessage] = useState('');
  const [updateUserRights] = useMutation(UPDATE_USER_RIGHTS);
  const [createOrganization] = useMutation(CREATE_ORGANIZATION);
  const [deleteUserFromOrganization] = useMutation(REMOVE_USER_FROM_ORG);
  const userId = useGetUserIDbyEmail(roleEmail).data.userId;

  const handleCreateOrganization = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!orgName) {
      setErrorMessage('Alle Felder müssen ausgefüllt werden!');
      return;
    }
    if (!loginStatus.loggedIn){
      return;
    }

    try {
      const { data } = await createOrganization({
        variables: {
          name: orgName,
          users: [loginStatus.user?.id],
          agb: "",
          physicalobjects: [""],
          location: "Everywhere"
        }
      });

      if (data?.createOrganization?.ok) {
        setErrorMessage('');
        alert('Organisation erfolgreich erstellt!');
        setOrganizationModalOpen(false);

        if (refetch) {
          refetch({ organizationIds: [selectedOrganizationId] });
        } else {
          fetchUsers({ variables: { organizationIds: [selectedOrganizationId] } });
        }
      } else {
        setErrorMessage(data?.createOrganization?.infoText || 'Organisationserstellung fehlgeschlagen.');
      }
    } catch (error) {
      setErrorMessage('Fehler bei der Organisationserstellung. Bitte versuche es später erneut.');
    }
  };
  
  const handleRoleChange = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!roleEmail) {
      setErrorMessage('Alle Felder müssen ausgefüllt werden!');
      return;
    }

    try {
      const { data } = await updateUserRights({
        variables: {
          newRights: selectedRole,
          organizationId: selectedOrganizationId,
          userId: userId
        }
      });

      if (data?.updateUserRights?.ok) {
        setErrorMessage('');
        alert('Rechte erfolgreich geändert!');
        setRoleModalOpen(false);
        refetch({ organizationIds: [selectedOrganizationId] });
        fetchUsers({ variables: { organizationIds: [selectedOrganizationId] } });
        if (refetch) {
          refetch({ organizationIds: [selectedOrganizationId] });
        } else {
          fetchUsers({ variables: { organizationIds: [selectedOrganizationId] } });
        }
      } else {
        setErrorMessage(data?.updateUserRights?.infoText || 'Rechteänderung fehlgeschlagen.');
      }
    } catch (error) {
      setErrorMessage('Fehler bei der Rechteänderung. Bitte versuche es später erneut.');
    }
  };

  const handleDeleteUserFromOrg = async (event: React.FormEvent) => {
    event.preventDefault();

    try {
      const { data } = await deleteUserFromOrganization({
        variables: {
          organizationId: selectedOrganizationId,
          userId: userId
        }
      });

      if (data?.removeUserFromOrganization?.ok) {
        setErrorMessage('');
        alert('Nutzer erfolgreich entfernt!');
        setUserDeleteOpen(false);

        if (refetch) {
          refetch({ organizationIds: [selectedOrganizationId] });
        } else {
          fetchUsers({ variables: { organizationIds: [selectedOrganizationId] } });
        }
      } else {
        setErrorMessage(data?.removeUserFromOrganization?.infoText || 'Entfernen des Nutzers fehlgeschlagen.');
      }
    } catch (error) {
      setErrorMessage('Fehler bei der Anfrage. Bitte versuche es später erneut.');
    }
  };



  const handleOrganizationChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newOrgId = e.target.value;
    startTransition(() => {
      setSelectedOrganizationId(newOrgId);
    });
  };


const [fetchUsers, { refetch }] = useLazyQuery(GET_USERS);


interface GetOrgByIdResponse {
  firstName: string,
  lastName: string,
  email: string,
  userId: string,
  rights: string,
  organizations: {
      edges: {
          node: {
                  organizationId: string,
                  rights: string,
              }
          }[]
  }
}

interface UserOrg {
    firstName: string,
    lastName: string,
    email: string,
    userId: string,
    rights: string,
    organizationId: {
      edges: {
          node: {
                  organizationId: string;
                  rights: string;
              }
          }[]
  }
}


const ORGANIZATIONS2 = loginStatus?.loggedIn ? loginStatus.user?.organizationInfoList : [];


function useGetAllUsersInOrganization(orgId: string[]) {
  const mapToGroup = (response: GetOrgByIdResponse[]): UserOrg[] => {
      return response.map(orgRes => ({
          firstName: orgRes.firstName,
          userId: orgRes.userId,
          lastName: orgRes.lastName,
          email: orgRes.email,
          organizationId: orgRes.organizations,
          rights: orgRes.organizations?.edges?.[0]?.node.rights
          }));
  };

  return useSuspenseQueryWithResponseMapped(
      GET_USERS,
      'filterUsers',
      { variables: { organizationIds: orgId } },
      mapToGroup
  );
};

    const { data: organizationUsers} = useGetAllUsersInOrganization(
      selectedOrganizationId ? [selectedOrganizationId] : []
    );
    const filteredUsers = (organizationUsers || []).filter(user =>
      user.firstName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      user.lastName.toLowerCase().includes(searchTerm.toLowerCase())
    );

const [selectedUser, setSelectedUser] = useState<UserOrg | null>(null); // New state to track selected user


const handleUserEdit = (user: UserOrg) => {
  setSelectedUser(user); // Set selected user for editing
  startTransition(() => {
    setRoleEmail(user.email); // Pre-fill email in the modal
  });
  setRoleModalOpen(true); // Open the modal
};

const handleUserDelete = (user: UserOrg) => {
  setSelectedUser(user); // Set selected user for editing
  startTransition(() => {
    setRoleEmail(user.email); // Pre-fill email in the modal
  });
  setUserDeleteOpen(true); // Open the modal
};

const getUserRightsForOrganization = (user: UserOrg): string => {
  if (!user.organizationId?.edges) return "--"; // Handle missing data

  const matchedOrg = user.organizationId.edges.find(
    edge => edge.node.organizationId === selectedOrganizationId
  );

  return matchedOrg ? matchedOrg.node.rights : "--"; // Return rights if found, otherwise "--"
};



  if (!loginStatus.loggedIn) {
    return <Login onClose={() => {}} />;
  }

  if(!(["ORGANIZATION_ADMIN", "SYSTEM_ADMIN"].includes(highestUserRights))){
    return (<h3 style={{ textAlign: "center", color: "#333" }}>Unzureichende Rechte</h3>);
  }

  return (
    <div style={{ marginTop: "30px", fontFamily: "Arial, sans-serif" }}>
      <h2 style={{ textAlign: "center", color: "#333" }}>Organisationsverwaltung</h2>
      <label style={{ fontWeight: "bold" }}>Organisation wählen:</label>
      <select 
        value={selectedOrganizationId}
        onChange={handleOrganizationChange}
        style={{ padding: "8px", margin: "10px 0", borderRadius: "5px", border: "1px solid #ccc" }}
      >
        <option >
          Organisation auswählen
        </option>
        {ORGANIZATIONS2.map((org) => (
           <option key={org.id} value={org.id}>
             {GetOrgName(org.id).data.name}
          </option> 
        ))}
      </select>

      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "10px" }}>
        <h3 style={{ color: "#444", margin: 0 }}>Mitglieder</h3>
        <input
          type="text"
          placeholder="Benutzer suchen..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{ padding: "8px", borderRadius: "5px", border: "1px solid #ccc", width: "250px" }}
        />
        <button onClick={() => {setRoleModalOpen(true); setSelectedUser(null); setRoleEmail("");}} style={{ padding: "8px 12px", borderRadius: "5px", backgroundColor: "#007bff", color: "white", border: "none", cursor: "pointer" }}>
          Benutzer hinzufügen
        </button>
        {["SYSTEM_ADMIN"].includes(highestUserRights) && (
        <button onClick={() => {setOrganizationModalOpen(true); setSelectedUser(null); setRoleEmail("");}} style={{ padding: "8px 12px", borderRadius: "5px", backgroundColor: "#007bff", color: "white", border: "none", cursor: "pointer" }}>
          Organisation erstellen
        </button>)}
      </div>

      <table className="organization-table" style={{ width: "100%", borderCollapse: "collapse", marginTop: "10px" }}>
        <thead>
          <tr style={{ backgroundColor: "#f4f4f4", borderBottom: "2px solid #ddd" }}>
            <th style={{ padding: "10px", textAlign: "left", width:"300px" }}>Vorname</th>
            <th style={{ padding: "10px", textAlign: "left", width:"300px"  }}>Nachname</th>
            <th style={{ padding: "10px", textAlign: "left", width: "300px"  }}>E-Mail</th>
            <th style={{ padding: "10px", textAlign: "left", width: "400px" }}>Rechte</th>
            <th style={{ padding: "10px", textAlign: "left"}}>Aktionen</th>
          </tr>
        </thead>
        <tbody>
          {filteredUsers.length > 0 ? (
            filteredUsers.map((user, index) => (
              <tr key={index} style={{ borderBottom: "1px solid #ddd" }}>
                <td style={{ padding: "10px" }}>{user.firstName}</td>
                <td style={{ padding: "10px" }}>{user.lastName}</td>
                <td style={{ padding: "10px" }}>{user.email}</td>
                <td style={{ padding: "10px" }}>{getUserRightsForOrganization(user) || "--"}</td>
                <td style={{ padding: "10px" }}>
                  <button style={{ marginRight: "5px", backgroundColor: "#28a745", color: "white", border: "none", padding: "5px", borderRadius: "5px", cursor: "pointer" }}
                  onClick={() => handleUserEdit(user)}>
                    <FaUserEdit />
                  </button>
                  <button style={{ backgroundColor: "#dc3545", color: "white", border: "none", padding: "5px", borderRadius: "5px", cursor: "pointer" }}
                  onClick={() => handleUserDelete(user)}>
                    <FaTrash />
                  </button>
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td  colSpan={5} style={{ padding: "10px", textAlign: "center", color: "#888"}}>Keine Benutzer gefunden</td>
            </tr>
          )}
        </tbody>
      </table>


      {isRoleModalOpen && (
        <div className="modal222">
          <div className="modal-content222">
          <h3>{selectedUser ? `Rechte verändern (${selectedUser.firstName} ${selectedUser.lastName})` : "Benutzer hinzufügen"}</h3>            <label>
              E-Mail des Nutzers:
              <input 
                type="email" 
                value={roleEmail} 
                onChange={(e) => {
                  const newEmail = e.target.value;
                  startTransition(() => {
                    setRoleEmail(newEmail);
                  });
                }}  
                placeholder="Benutzer E-Mail"
              />
            </label>
            <br /><br />
            <label>
              Rolle:
              <select value={selectedRole} onChange={(e) => setSelectedRole(e.target.value)}>
                <option value="organization_admin">Organization-Admin</option>
                <option value="inventory_admin">Inventory-Admin</option>
                <option value="member">Member</option>
                <option value="customer">Customer</option>
                <option value="watcher">Watcher</option>
              </select>
            </label>
            <br />
            {errorMessage && <p className="error-message">{errorMessage}</p>}
            <div className="modal-buttons">
              <button onClick={handleRoleChange}>Bestätigen</button>
              <button onClick={() => {setRoleModalOpen(false); setErrorMessage("")}}>Abbrechen</button>
            </div>
          </div>
        </div>
      )}
      {isOrganizationModalOpen && (
        <div className="modal222">
          <div className="modal-content222">
          <h3>{selectedUser ? `Rechte verändern (${selectedUser.firstName} ${selectedUser.lastName})` : "Organisation erstellen"}</h3>            <label>
              Name:
              <input 
                type="orgName" 
                value={orgName} 
                onChange={(e) => {
                  const orgName = e.target.value;
                  startTransition(() => {
                    setOrgName(orgName);
                  });
                }}  
                placeholder="Name der Organisation"
              />
            </label>
            <br />
            {errorMessage && <p className="error-message">{errorMessage}</p>}
            <div className="modal-buttons">
              <button onClick={handleCreateOrganization}>Bestätigen</button>
              <button onClick={() => {setOrganizationModalOpen(false); setErrorMessage("")}}>Abbrechen</button>
            </div>
          </div>
        </div>
      )}
      {isUserDeleteOpen && (
        <div className="modal222">
          <div className="modal-content222">
          <h3>{`Nutzer (${selectedUser?.firstName} ${selectedUser?.lastName}) aus der Organisation entfernen?`}</h3>            <label>
            </label>
            {errorMessage && <p className="error-message">{errorMessage}</p>}
            <div className="modal-buttons">
              <button onClick={handleDeleteUserFromOrg}>Bestätigen</button>
              <button onClick={() => {setUserDeleteOpen(false); setErrorMessage("")}}>Abbrechen</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
