import { useEffect, useState } from 'react';
import { gql, useApolloClient } from '@apollo/client';
import { format, startOfDay, startOfToday } from 'date-fns';

export interface BusyRange {
  physId: string;
  fromDate: string;
  tillDate: string;
  pending: boolean;
}

// Public query: busy date ranges per object, no order or person data
const GET_OBJECT_AVAILABILITY = gql`
  query CatalogueAvailability($physIds: [String]!) {
    objectAvailability(physIds: $physIds) {
      physId
      fromDate
      tillDate
      pending
    }
  }
`;

// Server limit per request
const MAX_IDS_PER_REQUEST = 200;
const MAX_UPCOMING_SHOWN = 3;

/**
 * Loads the busy ranges of the given objects (batched) and returns them grouped by object id.
 */
export function useAvailability(physIds: string[]): Map<string, BusyRange[]> {
  const client = useApolloClient();
  const [ranges, setRanges] = useState<Map<string, BusyRange[]>>(new Map());
  const key = Array.from(new Set(physIds)).sort((a, b) => a.localeCompare(b)).join(',');

  useEffect(() => {
    const ids = key ? key.split(',') : [];
    let cancelled = false;
    const chunks: string[][] = [];
    for (let i = 0; i < ids.length; i += MAX_IDS_PER_REQUEST) {
      chunks.push(ids.slice(i, i + MAX_IDS_PER_REQUEST));
    }
    Promise.all(chunks.map((chunk) => client.query<{ objectAvailability: BusyRange[] }>({
      query: GET_OBJECT_AVAILABILITY,
      variables: { physIds: chunk },
      fetchPolicy: 'network-only',
    }))).then((results) => {
      if (cancelled) return;
      const byId = new Map<string, BusyRange[]>();
      results.flatMap((result) => result.data?.objectAvailability ?? []).forEach((range) => {
        byId.set(range.physId, [...(byId.get(range.physId) ?? []), range]);
      });
      setRanges(byId);
    }).catch(() => {
      // availability is informational; the catalogue stays usable without it
      if (!cancelled) setRanges(new Map());
    });
    return () => { cancelled = true; };
  }, [client, key]);

  return ranges;
}

const day = (value: string) => startOfDay(new Date(value));
const formatDay = (value: string) => format(new Date(value), 'dd.MM.yyyy');

/** Confirmed range covering today, if any. */
export function currentLoan(ranges: BusyRange[]): BusyRange | undefined {
  const today = startOfToday();
  return ranges.find((r) => !r.pending && day(r.fromDate) <= today && day(r.tillDate) >= today);
}

const infoStyle: React.CSSProperties = { fontSize: '14px', marginTop: '4px' };

/**
 * Availability state of one object: "currently lent out until ..." plus the next booked ranges.
 */
export function AvailabilityInfo({ ranges }: Readonly<{ ranges: BusyRange[] }>) {
  const today = startOfToday();
  const loan = currentLoan(ranges);
  const upcoming = ranges
    .filter((r) => r !== loan && day(r.tillDate) >= today)
    .sort((a, b) => day(a.fromDate).getTime() - day(b.fromDate).getTime());

  return (
    <div style={infoStyle} className="availability-info">
      {loan
        ? <div style={{ color: '#b45309', fontWeight: 'bold' }}>Derzeit ausgeliehen bis {formatDay(loan.tillDate)}</div>
        : <div style={{ color: '#15803d' }}>Derzeit verfügbar</div>}
      {upcoming.slice(0, MAX_UPCOMING_SHOWN).map((r) => (
        <div key={`${r.fromDate}-${r.tillDate}`}>
          {r.pending ? 'Angefragt' : 'Gebucht'}: {formatDay(r.fromDate)} – {formatDay(r.tillDate)}
        </div>
      ))}
      {upcoming.length > MAX_UPCOMING_SHOWN && <div>… und {upcoming.length - MAX_UPCOMING_SHOWN} weitere Buchungen</div>}
    </div>
  );
}

/** Availability state of a group: how many of its objects are lent out today. */
export function GroupAvailabilityInfo(
  { memberIds, ranges }: Readonly<{ memberIds: string[]; ranges: Map<string, BusyRange[]> }>,
) {
  const lentOut = memberIds.filter((id) => currentLoan(ranges.get(id) ?? []) !== undefined).length;
  if (lentOut === 0) {
    return <div style={{ ...infoStyle, color: '#15803d' }} className="availability-info">Derzeit verfügbar</div>;
  }
  return (
    <div style={{ ...infoStyle, color: '#b45309', fontWeight: 'bold' }} className="availability-info">
      {lentOut} von {memberIds.length} Objekten derzeit ausgeliehen
    </div>
  );
}
