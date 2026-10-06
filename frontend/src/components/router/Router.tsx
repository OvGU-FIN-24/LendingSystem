import { Routes, Route } from "react-router-dom";
import { Layout } from "./Layout";
import { NotFound } from "../not-found/NotFound";
import { Inventory } from "../inventory/Inventory";
import { Cart } from "../cart/Cart";
import { AddInventory } from "../add-inventory/AddInventory";
import { EditInventory } from "../edit-inventory/EditInventory";
import { Login } from "../login/Login";
import { ResetPassword } from "../login/ResetPassword";
import { Requests } from "../requests/Requests";
import { InternalInventory } from "../internal-inventory/InternalInventory";
import { AddGroup } from "../add-group/AddGroup";
import { EditGroup } from "../edit-group/EditGroup";
import { EditRequest } from "../../components/requests/EditRequest";
import { Calendar } from "../calendar/Calendar";
import { ContactScreen } from "../contact/Contact";
import { ImpressumScreen } from "../impressum/Impressum";
import { PrivacyScreen } from "../privacy/Privacy";
import { Profile } from "../profile/Profile";
import { Suspense } from "react";
import { CheckLoginCart } from "../cart/CheckLoginCart";
import { OrganizationManagement } from "../profile/organizationManagement";

export function Router() {
    return (
        <Routes>
          <Route path='/' element={<Layout />}>
            <Route index element={<Inventory />}/>
            <Route path='contact' element={<ContactScreen />}/>
            <Route path='impressum' element={<ImpressumScreen />}/>
            <Route path='privacy' element={<PrivacyScreen />}/>
            <Route path='cart' element={<CheckLoginCart />}/>
            <Route path='profile' element={<Profile />}/>
            <Route path='organization' element={<OrganizationManagement />}/>
            <Route path='*' element={<NotFound />} />
    
            <Route path='inventory'>
              <Route index element={<Inventory />} />
              <Route path="group">
                <Route path="add/:orgId" element={<AddGroup />} />
                <Route path="edit/:groupId" element={<EditGroup />} />
              </Route>
              <Route path="add/:orgId" element={<AddInventory />} />
              <Route path="edit/:itemId" element={<EditInventory />} />
            </Route>

            <Route path='internal'>
              <Route path='inventory' element={<Suspense><InternalInventory /></Suspense>} />
              <Route path='calendar' element={<Calendar />} />
            </Route>

            <Route path='login' element={<Login onClose={() => {}}/>}/>
            <Route path='reset-password' element={<ResetPassword />}/>
            <Route path='requests' element={<Requests />}/>

            <Route path='requests'>
              <Route path='edit/:orderId' element={<EditRequest/>}/>
            </Route>
          </Route>
        </Routes>
      );
}