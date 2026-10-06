import React, { useState,useEffect } from 'react';
import { useQuery, gql } from '@apollo/client';
import 'react-day-picker/dist/style.css'
import { DateRange, DayPicker } from 'react-day-picker';
import { addDays, format, startOfToday } from 'date-fns';

interface Dates {
  fromDate: string;
  tillDate: string;
}

interface AvailabilityResponse {
  objectAvailability: Dates[];
}

type CalendarProbs = {
  fromDate : Date | null;
  tillDate : Date | null;
  setStartDate : (date: Date | null) => void;
  setEndDate : (date: Date | null) => void;
  physicalobjects : string[];
}

// Public query: busy date ranges of the given objects only
const GET_DATES = gql(/* GraphQL */ `
  query ObjectAvailability($physIds: [String]!) {
    objectAvailability(physIds: $physIds) {
      fromDate
      tillDate
    }
  }
`);

/**
 * 
 * @param probs to display dynamic date for the cart
 * @returns calendar where you can set a range of 2 dates that will be needed to know how long the object will be loaned
 */
export default function Calendar_Querry(probs: CalendarProbs) {
    const { loading, error, data } = useQuery<AvailabilityResponse>(GET_DATES, {
      variables: { physIds: probs.physicalobjects },
      skip: probs.physicalobjects.length === 0,
      fetchPolicy: 'network-only',
    });

    const defaultSelected: DateRange = {
      from: probs.fromDate!,
      to: probs.tillDate!
      };

    const [range, setRange] = useState<DateRange | undefined>(defaultSelected);

    useEffect(() => {
      probs.setStartDate(range?.from || null);
      probs.setEndDate(range?.to || null);
    }, [range]);

    let footer = <p>Please pick the first day.</p>;
    if (range?.from) {
      if (!range.to) {
        footer = <p>{format(range.from, 'PPP')}</p>;
      } else if (range.to) {
        footer = (
          <p>
            {format(range.from, 'PPP')}–{format(range.to, 'PPP')}
          </p>
        );
      }
    }

    if (loading) return <p>Loading...</p>;
    if (error) return <p>Error : {error.message}</p>;


    const css = `

    .my-selected:not([disabled]) { 
      font-weight: bold; 
      border: 2px solid black;
      color: black;
      background-color: magenta;
    }
    .my-selected:hover:not([disabled]) { 
      border-color: purple;
      color: magenta;
      background-color: white;
    }
    .my-today { 
      font-weight: bold;
      font-size: 140%; 
      color: orange;
    }

  `;


  const today = startOfToday();

  /**
   * disables all the dates before today and that are fetched from the querry
   **/
  const disabledDates = [
    { from: new Date(0), to: addDays(today, -1) },
    ...(data?.objectAvailability.map(order => ({
      from: new Date(order.fromDate),
      to: new Date(order.tillDate),
    })) || []),
  ];

  let additionalDisabledDates: { from: Date; to: Date; }[] = [];


  /**
   * disables all the dates before the selected date and until the first order is reached in the calendar
   */
  if (range && (range.from !==null)) {
    const closestDate = data?.objectAvailability.reduce((closest, current) => {
      const from = new Date(current.fromDate);
      if (from < range.from!) {
        return closest
      }
      return from < closest ? from : closest;
    }, new Date(8640000000000000));
    
    if(closestDate){
      additionalDisabledDates = [
        { from: new Date(0), to: addDays(range.from!, -1) },
        { from: addDays(closestDate, 1), to: new Date(8640000000000000) },
      ];
    }
  }


  const combinedDisabledDates = [...disabledDates, ...additionalDisabledDates];



    return(
        <>
    <style>{css}</style>
    <DayPicker
      styles={{
        button : { borderRadius: 20},
        
      }}
      id="test"
      mode="range"
      selected={range}
      footer={footer}
      onSelect={setRange}
      disabled={combinedDisabledDates}
      modifiersStyles={{
        disabled: { fontSize: '75%' }
      }}
      modifiersClassNames={{
        selected: 'my-selected',
        today: 'my-today'
      }}
    />
    </>
  );
}