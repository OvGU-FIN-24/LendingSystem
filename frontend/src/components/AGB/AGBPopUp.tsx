import React from "react";
import './../../core/input/Buttons/ButtonStyle.css';
import { useState, useEffect, useRef } from 'react';
import '../cart/OrderPopup.css';
import { Worker, Viewer } from '@react-pdf-viewer/core';
import { safePdfParams } from '../../utils/pdf';
import { zoomPlugin, RenderZoomInProps, RenderZoomOutProps } from '@react-pdf-viewer/zoom';
import '@react-pdf-viewer/core/lib/styles/index.css';
import '@react-pdf-viewer/default-layout/lib/styles/index.css';
import { OrderPopup } from "../cart/OrderPopup";
import {useGetOrganizationByIdQuery} from '../../hooks/organization-helper';
import { useNavigate } from "react-router-dom";

import { useQuery, gql, useMutation,} from '@apollo/client';
import { useLoginStatus, useUserInfo } from "../../context/LoginStatusContext";
import { ALL } from "dns";
import { InventoryItemInCart } from "../../models/InventoryItem.model";
import { User } from "../../models/user.model";
import { useCreateOrder } from "../../hooks/order-helper";
import { useGetUserLazy } from "../../hooks/user-helper";


type AGBPopUpProbs = {
    trigger : boolean,
    setTrigger : any,
    allProducts: InventoryItemInCart[][],
    products: InventoryItemInCart[],
    deposit: number,
    successFunc: ()=>void,
}

/**
 * 
 * @param props trigger as a boolean and setTrigger to change the boolean to show or not show the PopUp
 * @returns a PopUp where the user needs to read the AGB before loaning
 */
export default function AGBPopUp(props : AGBPopUpProbs){
    const navigate = useNavigate();
    //console.log(props);
    const [buttonPopup, SetButtonPopup] = useState(false);
    const [Close, setClose] = useState(false);
    const [isChecked, setIsChecked] = useState(false);
    const [text, setText] = useState<string[]>([]);
    const textRef = useRef<HTMLDivElement>(null);
    const zoomPluginInstance = zoomPlugin();

    const {data: org} = useGetOrganizationByIdQuery(props.products[0]?.organizationId ?? "00000000-0000-0000-0000-000000000003");
    console.log(org);
    /*if (org.agb==""){
        setIsChecked(true);
        setClose(true);
    }*/

    const status = useLoginStatus();
    if (status.loggedIn && status.user.organizationInfoList.filter(obj => obj.agbDontShow).map(obj => obj.id).includes(org.id)){
        setIsChecked(true);
        setClose(true);
    }

    const [createOrder] = useCreateOrder();

    const handleCreateOrder = async () => {
        try{
            const ids = props.products.map(item => {
                return item.physId;
            })

            const startDateUtc = props.products[0]?.startDate ?? null;
            const endDateUtc = props.products[0]?.endDate ?? null;

            if (startDateUtc!=null){
                startDateUtc.setHours(startDateUtc.getHours() + 2);
            }
            if (endDateUtc!=null){
                endDateUtc.setHours(endDateUtc.getHours() + 2);
            }

            const { data } = await createOrder({variables: {
                deposit: props.deposit,
                fromDate: startDateUtc,
                tillDate: endDateUtc,
                physicalobjects: ids,
            }});

            const ind = props.allProducts.indexOf(props.products);
            props.allProducts.splice(ind, 1);
            navigate(0);

            console.log("created successfully: ", data);
            props.successFunc();
        }
        catch(error){
            console.log("Error Order Create");
        }
    };

    useEffect(() => {
        if (!props.trigger) return;

        const element = textRef.current;

        if (!element) return;

        const handleScroll = () => {
            const tolerance = 10; 
            const isAtBottom = element.scrollHeight - element.scrollTop <= element.clientHeight + tolerance;
            setClose(isAtBottom);
        };

        element.addEventListener('scroll', handleScroll);
        handleScroll(); 

        return () => {
            element.removeEventListener('scroll', handleScroll);
        };
    }, [props.trigger]);


    useEffect(() => {
        if (props.trigger) {
            setIsChecked(false);
            setClose(false);
        }
    }, [props.trigger]);


    const handleCheckboxChange = () => {
        setIsChecked(!isChecked);
    };

    const { ZoomIn, ZoomOut } = zoomPluginInstance;

    return (
        props.trigger ?
            <div className="overlay">
                <div className="popup">
                    <div 
                        ref={textRef} 
                        style={{ margin: 0, padding: '10px', maxHeight: '400px', overflowY: 'auto' }}
                    >
                {/*      {text.map((paragraph, index) => (
                            <p key={index} dangerouslySetInnerHTML={{ __html: paragraph }}></p>
                        ))}*/}
                        { org.agb!="" &&
                          <div>
                            <Worker workerUrl='/pdf.worker.min.js'>
                                <Viewer fileUrl={process.env.REACT_APP_PDFS_BASE_URL+org.agb}  plugins={[zoomPluginInstance]} transformGetDocumentParams={safePdfParams}/>
                            </Worker>
                            <div style={{ marginTop: '10px' }}>
                                    <input
                                        type="checkbox"
                                        id="agreeCheckbox"
                                        style={{  marginRight: "10px", width: "auto"}}
                                        checked={isChecked}
                                        onChange={handleCheckboxChange}
                                    />
                                <label htmlFor="agreeCheckbox">Ich stimme den AGB zu.</label>
                            </div>
                          </div>
                        }
                        { org.agb=="" &&
                            <div>Es gibt keine AGB.</div>
                        }
                    </div>
                    
                    <div>
                    <button 
                        onClick={() => {handleCreateOrder(); 
                            props.setTrigger(false);}}
                        disabled={!(isChecked)}
                    >
                        Akzeptieren
                    </button>
                    <button
                        onClick={() => {props.setTrigger(false)}}>
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
            
        : <OrderPopup trigger={buttonPopup} setTrigger={SetButtonPopup}/>
    );
}
const buttonContainerStyle: React.CSSProperties = {
    textAlign: 'right',
};
const input: React.CSSProperties = {
    padding: '10px',
    width: '100%',
    marginRight: '10px',
};
const inputCheckbox: React.CSSProperties = {
    marginRight: '10px',
};