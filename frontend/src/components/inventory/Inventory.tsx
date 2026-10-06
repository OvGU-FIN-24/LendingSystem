import React, { useState, useEffect, useRef, Suspense } from 'react';
import Calendar from '../../core/input/Buttons/Calendar';
import Calendar_Querry from '../../core/input/Buttons/Calendar_Querry';
import { useCart, useCartDispatcher } from '../../context/CartContext';

import { useQuery, gql } from '@apollo/client';
import { useGetPhysicalObjects } from '../../hooks/pysical-object-helpers';
import { useGetTagsQuery } from '../../hooks/tag-helpers';
import { useGetAllGroupsQuery } from '../../hooks/group-helpers';
import { useGetAllOrganizations } from '../../hooks/organization-helper';
import { Console, group } from 'console';
import { InventoryItem } from '../../models/InventoryItem.model';

import { Worker, Viewer } from '@react-pdf-viewer/core';
import { zoomPlugin, RenderZoomInProps, RenderZoomOutProps } from '@react-pdf-viewer/zoom';
import '@react-pdf-viewer/core/lib/styles/index.css';
import '@react-pdf-viewer/default-layout/lib/styles/index.css';
import packageJson from '../../../package.json';

import CalendarQuerryNew from "../../core/input/Buttons/Calendar_Querry_New";
import { useLoginStatus } from "../../context/LoginStatusContext";
import { AvailabilityInfo, GroupAvailabilityInfo, useAvailability } from "./Availability";

export function Inventory(): JSX.Element {
  const loginDispatcher = useLoginStatus();
  const itemsInCart = useCart();
  const itemsInCartDispatcher = useCartDispatcher();

  // Fetching physical objects
  const { data: products_tmp, error } = useGetPhysicalObjects();
  const { data: tags, error: e } = useGetTagsQuery();
  const { data: orgs, error: e3} = useGetAllOrganizations();
  const { data: groups, error: e2} = useGetAllGroupsQuery();
  const products = products_tmp.concat(groups);
  products.sort(function(a, b){
      if (a.name.toLowerCase()<b.name.toLowerCase()) return -1;
      if (a.name.toLowerCase()>b.name.toLowerCase()) return 1;
      return 0;
    }
  );
  products.map(product => {
    product.physicalObjects?.sort(function(a, b){
      if (a.name.toLowerCase()<b.name.toLowerCase()) return -1;
      if (a.name.toLowerCase()>b.name.toLowerCase()) return 1;
      return 0;
    });
    return product;
  });
  console.log(products);

  // Public availability (dates only) of every listed object, including group members
  const availability = useAvailability(products.flatMap(product =>
    product.physId.startsWith("group")
      ? (product.physicalObjects ?? []).map(obj => obj.physId)
      : [product.physId]));

  const [showModal, setShowModal] = useState<boolean>(false);
  const [selectedProduct, setSelectedProduct] = useState<InventoryItem | null>(null);
  const [startDate, setStartDate] = useState<Date | null>(null);
  const [endDate, setEndDate] = useState<Date | null>(null);
  const [physicalObjectIds, setPhysicalObjectIds] = useState<string[]>([]);
  const [amount, setAmount] = useState<number>(1);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [selectedOrganizations, setSelectedOrganizations] = useState<string[]>([]);
  const [dropdownVisible, setDropdownVisible] = useState<boolean>(false);
  const [dropdownVisible2, setDropdownVisible2] = useState<boolean>(false);
  const [showManual, setShowManual] = useState<boolean>(false);
  const [selectedManualPath, setSelectedManualPath] = useState<string>("");
  const [showGroupElements, setShowGroupElements] = useState<boolean>(false);
  const [selectedGroup, setSelectedGroup] = useState<InventoryItem | null>(null);
  const [showPictures, setShowPictures] = useState<boolean>(false);
  const [selectedItemForPictures, setSelectedItemForPictures] = useState<InventoryItem | null>(null);

  const textRef = useRef<HTMLDivElement>(null);
  const zoomPluginInstance = zoomPlugin();

  const { ZoomIn, ZoomOut } = zoomPluginInstance;

  const dropdownRef = useRef<HTMLDivElement>(null);
  const dropdownRef2 = useRef<HTMLDivElement>(null);

  const pdfjsVersion = packageJson.dependencies['pdfjs-dist'];

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownVisible(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [dropdownRef]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef2.current && !dropdownRef2.current.contains(event.target as Node)) {
        setDropdownVisible2(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [dropdownRef2]);

  const openModal = (product: InventoryItem) => {
    setSelectedProduct(product);
    setShowModal(true);
    
    //ids.push(product.physId);
    if (product.physId.substring(0, 5)=="group"){
      product?.physicalObjects?.forEach(obj => {
        setPhysicalObjectIds(prevIds => [... prevIds, obj.physId]);
      });
    }
    else {
      setPhysicalObjectIds(prevIds => [... prevIds, product.physId]);
    }

    console.log("ids: " + physicalObjectIds);
  };

  const closeModal = () => {
    setShowModal(false);
    if (selectedProduct?.physId.substring(0, 5)=="group"){      
      setPhysicalObjectIds(prevIds => prevIds.filter(id => !selectedProduct.physicalObjects?.map(obj => obj.physId).includes(id)));
    }
    else {
      setPhysicalObjectIds(prevIds => prevIds.filter(id => id !== selectedProduct?.physId));
    }
    setSelectedProduct(null);

    console.log("ids: " + physicalObjectIds);
  };

  const openManual = (path: string | undefined) => {
    if (path!=undefined){
      setSelectedManualPath(path);
      setShowManual(true);
    }
  };

  const closeManual = () => {
    setShowManual(false);
    setSelectedManualPath("");
  };

  const openGroupElements = (group: InventoryItem) => {
    setSelectedGroup(group);
    setShowGroupElements(true);
  };

  const closeGroupElements = () => {
    setShowGroupElements(false);
    setSelectedGroup(null);
  };

  const openPictures = (product: InventoryItem) => {
    console.log("CLICKED ON PIC");
    if (product.images.length>1){
      setSelectedItemForPictures(product);
      setShowPictures(true);
    }
  };

  const closePictures = () => {
    setShowPictures(false);
    setSelectedItemForPictures(null);
  };

  const addToCart = () => {
    if (selectedProduct && startDate && endDate) {
      console.log(selectedProduct);
      if (selectedProduct.physId.substring(0, 5)=="group" && selectedProduct.physicalObjects!=undefined){
          selectedProduct.physicalObjects.forEach(obj => {
            itemsInCartDispatcher({
              type: 'add',
              item: { ...obj, startDate, endDate, amount}
            })
        });
      }
      else {
        itemsInCartDispatcher({
          type: 'add',
          item: { ...selectedProduct, startDate, endDate, amount }
        });
      }
      closeModal();
    }
    console.log(itemsInCart);
  };

  const handleCategoryChange = (category: string) => {
    setSelectedCategories(prevCategories =>
      prevCategories.includes(category)
        ? prevCategories.filter(c => c !== category)
        : [...prevCategories, category]
    );
  };
  const handleOrganizationChange = (org: string) => {
    setSelectedOrganizations(prevOrganizations =>
      prevOrganizations.includes(org)
        ? prevOrganizations.filter(c => c !== org)
        : [...prevOrganizations, org]
    );
  };

  const filteredProducts = products?.filter(product =>
    {
      var res: boolean = true;
      if (product.physId.substring(0, 5)=="group"){
        product.physicalObjects?.forEach(item => {
          if (itemsInCart.map(obj => obj.physId).includes(item.physId)){ 
            res=false;
          }
        });
      }
      
      return product.name.toLowerCase().includes(searchQuery.toLowerCase()) 
      && (selectedCategories.includes(product.category) || selectedCategories.length==0)
      && (selectedOrganizations.includes(product.organization) || selectedOrganizations.length==0)
      && (res)
      && (product.borrowable)
      && (!loginDispatcher.loggedIn || !(itemsInCart.map(obj => obj.physId).includes(product.physId)));
    }
  );

  if (error) return <p>Error loading products: {error.message}</p>;

  return (
    <Suspense>
      <div style={{ padding: '20px' }}>
        <div style={filterContainerStyle}>
          <input
            type="text"
            placeholder="Suchen"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={searchInputStyle}
          />
          <div style={{ position: 'relative', display: 'inline-block' }} ref={dropdownRef}>
            <button
              style={dropdownButtonStyle}
              onClick={() => setDropdownVisible(!dropdownVisible)}
            >
              Filter nach Kategorien
            </button>
            {dropdownVisible && (
              <div style={dropdownContentStyle}>
                { tags.map((ele) => (
                  <div style={checkboxLabelStyle}>
                    <input
                      id={ele.id}
                      type="checkbox"
                      style={{  marginRight: "10px", width: "auto"}}
                      checked={selectedCategories.includes(ele.tag)}
                      onChange={() => handleCategoryChange(ele.tag)}
                    />
                    <label htmlFor={ele.id}>{ele.tag}</label>
                    
                    
                  </div>
                ))}
              </div>
            )}
          </div>
          <div style={{ position: 'relative', display: 'inline-block', marginLeft: '10px'}} ref={dropdownRef2}>
            <button
              style={dropdownButtonStyle}
              onClick={() => setDropdownVisible2(!dropdownVisible2)}
            >
              Filter nach Organisationen
            </button>
            {dropdownVisible2 && (
              <div style={dropdownContentStyle}>
                { orgs.map((ele) => (
                  <div style={checkboxLabelStyle}>
                    <input
                      id={ele.id}
                      type="checkbox"
                      style={{  marginRight: "10px", width: "auto"}}
                      checked={selectedOrganizations.includes(ele.name)}
                      onChange={() => handleOrganizationChange(ele.name)}
                    />
                    <label htmlFor={ele.id}>{ele.name}</label>
                    
                    
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <div style={{ marginTop: '20px' }}>
          {filteredProducts.map((product) => (
            <div key={product.physId} style={productCardStyle}>
              {//'http://192.168.178.169/pictures/'<img src={'${process.env.REACT_APP_PICTURES_BASE_URL}' + product.images[0]?.path || 'https://via.placeholder.com/300'} alt={product.name} style={imageStyle} />
              }
              {product.images.length>1 &&
                <div style={{ position: 'relative', display: 'inline-block' }}>
                  <img src={(product.images.length>0)?process.env.REACT_APP_PICTURES_BASE_URL + product.images[0]?.path: process.env.REACT_APP_PICTURES_BASE_URL+'1741980710.2106326_platzhalter_bild.png'} alt={product.name} style={imageStyle} />
                  <button 
                    onClick={() => openPictures(product)}
                    style={{
                        color: 'rgba(0, 0, 0, 0.6)',
                        border: '1px solid #ccc',
                        marginTop: '10px',
                        marginRight: '10px',
                        width: '92%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '20px',
                        cursor: 'pointer'
                    }}
                    >
                      +
                  </button>
                </div>
              }
              {product.images.length<=1 &&
                <img src={(product.images.length>0)?process.env.REACT_APP_PICTURES_BASE_URL + product.images[0]?.path: process.env.REACT_APP_PICTURES_BASE_URL+'1741980710.2106326_platzhalter_bild.png'} alt={product.name} style={imageStyle} />
              }
              <div style={productInfoStyle}>
                <div style={descriptionStyle}>
                    {product.physId.substring(0, 5)=="group" &&
                        <h3>{product.name} (Gruppe)</h3>
                    }
                    {product.physId.substring(0, 5)!="group" &&
                        <h3>{product.name}</h3>
                    }
                  <div style={descriptionContentStyle}>{product.description}</div>
                </div>
                
                <div style={descriptionContentStyle}>Kaution: {product.deposit/100} €</div>
                <div style={descriptionContentStyle}>Organisation: {product.organization}</div>
                <div style={descriptionContentStyle}>Mängel: {product.defects}</div>
                {product.physId.startsWith("group")
                  ? <GroupAvailabilityInfo memberIds={(product.physicalObjects ?? []).map(obj => obj.physId)} ranges={availability} />
                  : <AvailabilityInfo ranges={availability.get(product.physId) ?? []} />}
                
                <div>
                  <button style={addToCartButtonStyle} onClick={() => openModal(product)}>
                    In den Warenkorb hinzufügen
                  </button>
                  {product.physId.substring(0, 5)=="group" && 
                    <button onClick={() => openGroupElements(product)} style={addToCartButtonStyle}>
                      Objekte der Gruppe anzeigen
                    </button>
                  }  
                  {product.manualPath!="" && 
                      <button onClick={() => openManual(product.manualPath)} style={addToCartButtonStyle}>
                        Anleitung
                      </button>
                  } 
                </div>
              </div>
            </div>
          ))}
        </div>
        
      </div>

      

      {showModal && (
          <div style={modalOverlayStyle}>
            <div style={modalContentStyle}>
              <h2>{selectedProduct?.name} hinzufügen</h2>
              
              <CalendarQuerryNew setEndDate={setEndDate} setStartDate={setStartDate} tillDate={endDate} fromDate={startDate} physicalobjects={physicalObjectIds}/>
      
              <div style={buttonContainerStyle}>
                <button onClick={addToCart} disabled={!startDate || !endDate}>Hinzufügen</button>
                <button onClick={closeModal} style={{ marginLeft: '10px' }}> Schließen </button>
              </div>
            </div>
          </div>
      )}

      {showGroupElements && (
          <div style={modalOverlayStyle}>
            <div style={modalContentStyle}>
              <h2>Objekte in {selectedGroup?.name}</h2>
              
              <div style={{ marginTop: '20px', maxHeight: '500px', overflowY: 'auto' }}>
                {selectedGroup?.physicalObjects!=undefined &&
                 selectedGroup?.physicalObjects.map((product) => (
                  <div key={product.physId} style={productCardStyle}>
                    {//<img src={'${process.env.REACT_APP_PICTURES_BASE_URL}' + product.images[0]?.path || 'https://via.placeholder.com/300'} alt={product.name} style={imageStyle} />
                    }
                    <img src={(product.images.length>0)?process.env.REACT_APP_PICTURES_BASE_URL + product.images[0]?.path: process.env.REACT_APP_PICTURES_BASE_URL + '1741980710.2106326_platzhalter_bild.png'} alt={product.name} style={imageStyle} />
                    <div style={productInfoStyle}>
                      <div style={descriptionStyle}>
                        <h3>{product.name}</h3>
                        <div style={descriptionContentStyle}>{product.description}</div>
                      </div>
                      
                      <div style={descriptionContentStyle}>Mängel: {product.defects}</div>
                      <AvailabilityInfo ranges={availability.get(product.physId) ?? []} />
                    </div>
                  </div>
                ))}
              </div>




              <div style={buttonContainerStyle}>
                <button onClick={closeGroupElements} style={{ marginLeft: '10px' }}> Schließen </button>
              </div>
            </div>
          </div>
      )} 

      {showManual && (
        <div style={modalOverlayStyle}>
          <div style={modalContentStyle}>
            <h2>Anleitung</h2>
            <div 
                    ref={textRef} 
                    style={{ margin: 0, padding: '10px', overflowY: 'auto' }}
                >
                  <Viewer fileUrl={process.env.REACT_APP_PDFS_BASE_URL + selectedManualPath}  plugins={[zoomPluginInstance]}/>
            </div>
            <div>
              <button
                  onClick={closeManual}>
                  Zurück
              </button>
              <ZoomIn>
              {(props: RenderZoomInProps) => <button onClick={props.onClick}>+</button>}
              </ZoomIn>
              <ZoomOut>
              {(props: RenderZoomOutProps) => <button onClick={props.onClick}>-</button>}
              </ZoomOut>
            </div>
          </div>
        </div>
      )}

      {showPictures && (
          <div style={modalOverlayStyle}>
            <div style={modalContentStyle}>
              <h2>Bilder zu {selectedItemForPictures?.name}</h2>
              
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', maxHeight: '500px', overflowY: 'auto' }}>
                { selectedItemForPictures?.images.map((pic) =>(

                  <div>
                    <img src={process.env.REACT_APP_PICTURES_BASE_URL + pic.path} style={imageStyle} />
                  </div>

                ))}
              </div>

              <div style={buttonContainerStyle}>
                <button onClick={closePictures} style={{ marginLeft: '10px' }}> Zurück </button>
              </div>
            </div>
          </div>
      )}

      </Suspense>
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
  marginBottom: '15px',
};

const productCardStyle: React.CSSProperties = {
  marginBottom: '20px',
  border: '1px solid #ccc',
  padding: '10px',
  display: 'flex',
  alignItems: 'center',
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
  display: 'grid',
  gridTemplateRows: 'auto 1fr auto',
  gridTemplateColumns: 'auto',
  width: '90%',
  height: '90%'
};

const inputContainerStyle: React.CSSProperties = {
  marginBottom: '20px',
};

const buttonContainerStyle: React.CSSProperties = {
  textAlign: 'right',
};

const linkStyle: React.CSSProperties = {
  padding: '0px',
  marginTop: '6px',
  marginBottom: '6px',
};