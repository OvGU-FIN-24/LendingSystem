import React, { Suspense } from "react";
import { OrderPopup } from "./OrderPopup";
import { useState, useEffect } from "react";
import './Cart.css';
import Calendar from '../../core/input/Buttons/Calendar';
import Calendar_Querry from "../../core/input/Buttons/Calendar_Querry";
import AGBPopUp from "../AGB/AGBPopUp";
import { useLoginStatus, useUserInfo } from "../../context/LoginStatusContext";

import { useQuery, gql } from '@apollo/client';
import { useCart, useCartDispatcher } from "../../context/CartContext";
import { Spinner } from "@blueprintjs/core";
import { InventoryItemInCart } from "../../models/InventoryItem.model";
import { useGetDepositForCart } from "../../hooks/deposit-helpers";
import { isTemplateMiddle } from "typescript";
import { useToaster } from '../../context/ToasterContext';


export function Cart() {
  const toaster = useToaster();
  const onSuccess = () => {
    toaster.show({ message: 'Bestellung erfolgreich erstellt', intent: 'success' });
  }

  const [GetMaxDeposit] = useGetDepositForCart();
  const user = useUserInfo();
  const itemsInCartUnsorted = useCart();
  itemsInCartUnsorted.sort(function(a , b){
      if (a.organization<b.organization) return -1;
      if (a.organization>b.organization) return 1;
      if (a.organization==b.organization){
        if (a.startDate<b.startDate) return -1;
        if (a.startDate>b.startDate) return 1;
        if (a.startDate==b.startDate){
          if (a.endDate<b.endDate) return -1;
          if (a.endDate>b.endDate) return 1;
        }
      }
      return 0;
    }
  );
  //console.log("CART");
  //console.log(itemsInCartUnsorted);

  const orgsInCart = [...new Set(itemsInCartUnsorted.map(item => item.organizationId))];
  const [maxDep, setMaxDep] = useState<{ organizationId: string; deposit: number }[]>([]);

  useEffect(() => {
    const fetchAllDeposits = async () => {
      const results = await Promise.all(
        orgsInCart.map(async (orgId) => {
          const userRig = user.organizationInfoList.find(org => org.id==orgId);
          //const userRig = {rights: "CUSTOMER"};
          const {data: deposit} = await GetMaxDeposit({
            variables: {
              organizationId: orgId,
              userRight: userRig?.rights ?? "CUSTOMER",
            },
          });

          return { organizationId: orgId, deposit: deposit.maxDeposit };
        })
      );

      setMaxDep(results);
    };

    fetchAllDeposits();
  }, []);
    
  console.log("TEST MUTATION");
  console.log(maxDep);

  const depositForOrg: number[] = [];
  const itemsInCart: InventoryItemInCart[][] = [];
  //const [depositForOrg, setDepositForOrg] = useState<number[]>([]);
  //const [itemsInCart, setItemsInCart] = useState<InventoryItemInCart[][]>([]);
  let firstOrg = itemsInCartUnsorted.length>0 ? itemsInCartUnsorted[0].organization : "";
  let firstStartDate = itemsInCartUnsorted.length>0 ? itemsInCartUnsorted[0].startDate: "";
  let firstEndDate = itemsInCartUnsorted.length>0 ? itemsInCartUnsorted[0].endDate: "";
  let maxD = 10000;
  if (itemsInCartUnsorted.length > 0) {
    itemsInCart.push([]);
    depositForOrg.push(0);
    //setItemsInCart(prevEle => [... prevEle, []]);
    //setDepositForOrg(prevEle => [... prevEle, 0]);
    maxD = maxDep.find(depForOrg => depForOrg.organizationId==itemsInCartUnsorted[0].organizationId)?.deposit ?? 10000; 
  }

  itemsInCartUnsorted.forEach(item => {
    const ind = itemsInCart.length-1;
    if (item.organization == firstOrg && item.startDate.toString() == firstStartDate.toString() && item.endDate.toString() == firstEndDate.toString()){
      itemsInCart[ind].push(item);
      depositForOrg[ind] += item.deposit;
      if (depositForOrg[ind]>maxD) depositForOrg[ind]=maxD;
    }
    else{
      maxD = maxDep.find(depForOrg => depForOrg.organizationId==item.organizationId)?.deposit ?? 10000;
      itemsInCart.push([]);
      depositForOrg.push(0);
      itemsInCart[ind+1].push(item);
      depositForOrg[ind+1] += item.deposit;
      if (depositForOrg[ind+1]>maxD) depositForOrg[ind+1]=maxD;
      firstOrg = item.organization;
      firstStartDate = item.startDate;
      firstEndDate = item.endDate;
    }
  });

  //console.log("AFTER SORT");
  //console.log(itemsInCart);
  const itemsInCartDispatcher = useCartDispatcher();
  const loginDispatcher = useLoginStatus();

    const [buttonPopup, SetButtonPopup] = useState(false);
    const [showModal, setShowModal] = useState<boolean>(false);
    const [selectedProduct, setSelectedProduct] = useState<InventoryItemInCart | null>(null);
    const [amount, setAmount] = useState<number>(1);
    const [startDate, setStartDate] = useState<Date | null>(null);
    const [endDate, setEndDate] = useState<Date | null>(null);

    var productNew: InventoryItemInCart;

     useEffect(() => {
       if (selectedProduct) {
          setStartDate(selectedProduct.startDate ?? null);
           setEndDate(selectedProduct.endDate ?? null);
       }
   }, [selectedProduct]);

    const openModal = (product: InventoryItemInCart) => {
        setSelectedProduct(product);
        setStartDate(product.startDate ?? null);
        setEndDate(product.endDate ?? null);
        setAmount(product.amount ?? 1);
        setShowModal(true);
    };
    const closeModal = () => {
        if(selectedProduct){
        setStartDate(selectedProduct?.startDate ?? null);
        setEndDate(selectedProduct?.endDate ?? null);
        setAmount(selectedProduct.amount ?? 1);
        }
        setShowModal(false);
        setSelectedProduct(null);
    };
    const editProduct = () => {
     if (selectedProduct && startDate && endDate){
        productNew = {...selectedProduct!,amount,startDate,endDate};
        itemsInCartDispatcher({ type: 'edit', item: productNew });
        setSelectedProduct(null);
        closeModal();
     }
    };

    

    
    return (
        
        <div>
            <div style={{padding: '20px'}}>
                <h2 style={{marginBottom: '20px'}}>Warenkorb</h2>


                {itemsInCart.map((item) => (
                  <div style={aroundProductCardStyle}>
                  {item.map((product) => (
                    <div key={product.physId} style={productCardStyle}>
                    <img src={(product.images.length>0)?process.env.REACT_APP_PICTURES_BASE_URL + product.images[0]?.path: process.env.REACT_APP_PICTURES_BASE_URL+'1741980710.2106326_platzhalter_bild.png'} alt={product.name} style={imageStyle} />
                    <div style={productInfoStyle}>
                      <h3>{product.name}</h3>
                      
                      <div style={descriptionStyle}>
                        <div style={descriptionContentStyle}>{product.description}</div>
                      </div>
                      <div style={priceStyle}>Kaution: {product.deposit/100} €</div>
                      <div>vom {product.startDate?.toLocaleDateString() ?? 'N/A'} bis zum {product.endDate?.toLocaleDateString() ?? 'N/A'}</div>
                      <div>Organistation: {product.organization}</div>

                      
                      {/**<button style={addToCartButtonStyle} onClick={() => openModal(product)}>
                        Bearbeiten
                      </button>*/}
                      <button style={addToCartButtonStyle} onClick={() => itemsInCartDispatcher({ type: 'remove', item: product })}>
                        Entfernen
                      </button>
                    </div>
                  </div>
                  ))}

                    <div style={priceStyle}>Kaution: {depositForOrg[itemsInCart.indexOf(item)]/100} €</div>
                    <button onClick={() => SetButtonPopup(true)} style={addToCartButtonStyle} >Abschicken</button>
                    
                    {<Suspense fallback={buttonPopup &&<Spinner/>}><AGBPopUp setTrigger={SetButtonPopup} trigger={buttonPopup} products={item} deposit={depositForOrg[itemsInCart.indexOf(item)]} allProducts={itemsInCart} successFunc={onSuccess}/></Suspense>}
                    {/*<OrderPopup trigger={buttonPopup} setTrigger={SetButtonPopup} />*/}
                  </div>
                
                ))}

                {showModal && (
                    <div style={modalOverlayStyle}>
                    <div style={modalContentStyle}>
                        <h2 //add calendar under here
                        >Objekt bearbeiten
                        </h2>
                        <Calendar_Querry setEndDate={setEndDate} setStartDate={setStartDate} tillDate={endDate} fromDate={startDate} physicalobjects={selectedProduct ? [selectedProduct.physId] : []}/>
                        

                        <div style={inputContainerStyle}>
                        <label>Menge:</label>
                        <input
                            
                            type="number"
                            value={amount}
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setAmount(parseInt(e.target.value))}
                            min="1"
                            style={{ marginLeft: '10px' }}
                        />
                        </div>
                        <div style={buttonContainerStyle}>
                        <button onClick={() => editProduct()}>Edit</button>
                        <button onClick={closeModal} style={{ marginLeft: '10px' }}>
                            Cancel
                        </button>
                        </div>
                    </div>
                    </div>
                )}
            
            </div>
        </div>
    );
  

}


const filterContainerStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    marginBottom: '20px',
  };
  
  const searchInputStyle: React.CSSProperties = {
    padding: '10px',
    width: '200px',
    marginRight: '10px',
  };
  
  const dropdownButtonStyle: React.CSSProperties = {
    padding: '10px 20px',
    backgroundColor: '#007bff',
    color: '#ffffff',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
  };
  
  const dropdownContentStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    position: 'absolute',
    backgroundColor: '#f1f1f1',
    minWidth: '160px',
    boxShadow: '0px 8px 16px 0px rgba(0,0,0,0.2)',
    padding: '12px 16px',
    zIndex: 1,
  };
  
  const checkboxLabelStyle: React.CSSProperties = {
    display: 'block',
    marginBottom: '10px',
  };
  
  const productCardStyle: React.CSSProperties = {
    marginBottom: '20px',
    border: '1px solid #ccc',
    padding: '10px',
    display: 'flex',
    alignItems: 'center',
  };

  const aroundProductCardStyle: React.CSSProperties = {
    marginBottom: '20px',
    border: '1px solid #ccc',
    padding: '10px',
  };
  
  const imageStyle: React.CSSProperties = {
    width: '250px',
    height: '150px',
    marginRight: '20px',
  };
  
  const productInfoStyle: React.CSSProperties = {
    flex: '1',
  };
  
  const addToCartButtonStyle: React.CSSProperties = {
    backgroundColor: '#007bff',
    color: '#ffffff',
    border: 'none',
    padding: '10px 20px',
    borderRadius: '4px',
    cursor: 'pointer',
    marginRight: '10px',
    marginTop: '10px',
  };

  const divTOSendButton: React.CSSProperties = {
    border: 'solid',
    marginBottom: '10px',
  };
  
  const descriptionStyle: React.CSSProperties = {
    marginBottom: '10px',
  };
  
  const descriptionButtonStyle: React.CSSProperties = {
    backgroundColor: '#fff',
    color: '#191970',
    border: 'none',
    padding: '2px 4px',
    borderRadius: '4px',
    cursor: 'pointer',
    marginRight: '10px',
    textDecoration: 'underline',
  };
  
  
  const descriptionContentStyle: React.CSSProperties = {
    //display: 'none',
  };
  
  
  const priceStyle: React.CSSProperties = {
    fontWeight: 'bold',
  };
  
  const modalOverlayStyle: React.CSSProperties = {
    position: 'fixed',
    top: '0',
    left: '0',
    right: '0',
    bottom: '0',
    backgroundColor: 'rgba(0,0,0,0.7)',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
  };
  
  const modalContentStyle: React.CSSProperties = {
    backgroundColor: '#fff',
    padding: '20px',
    borderRadius: '5px',
  };
  
  const inputContainerStyle: React.CSSProperties = {
    marginBottom: '20px',
  };
  
  const buttonContainerStyle: React.CSSProperties = {
    textAlign: 'right',
  };