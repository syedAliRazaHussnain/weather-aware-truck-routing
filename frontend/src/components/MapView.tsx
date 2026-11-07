// The map: heatmap squares, routes coloured by risk, checkpoint dots and popups.
// Everything is drawn as MapLibre layers (not React elements), and the heatmap
// slider only changes one colour rule, so panning and sliding stay smooth (#53).
import { type ExpressionSpecification, type FilterSpecification, setWorkerUrl } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useMemo, useRef } from 'react'
import Map, {
  Layer,
  type MapLayerMouseEvent,
  type MapRef,
  Marker,
  NavigationControl,
  Popup,
  Source,
} from 'react-map-gl/maplibre'
import type { Checkpoint, Place, PlanResult, RouteResult } from '../api/types'
import { levelColor, levelColorExpression } from '../lib/risk'
import { bounds } from '../lib/routes'
import { formatClock, zoneAbbreviation } from '../lib/time'

// MapLibre 6 finds its web worker next to its own file, which bundlers move; point
// it at the worker explicitly so it loads in development and in the built app.
setWorkerUrl(workerUrl)

const STYLE = 'https://tiles.openfreemap.org/styles/positron' // #56: light, free, no key
const START_VIEW = { longitude: -98.5, latitude: 39.5, zoom: 3.5 }

interface Props {
  plan: PlanResult | null
  origin: Place | null
  destination: Place | null
  selectedId: RouteResult['id'] | null
  hour: number
  openCheckpoint: number | null
  onSelectRoute: (id: RouteResult['id']) => void
  onOpenCheckpoint: (index: number | null) => void
  onCenter: (center: { lat: number; lon: number }) => void
}

export function MapView(props: Props) {
  const { plan, origin, destination, selectedId, hour, openCheckpoint } = props
  const map = useRef<MapRef>(null)

  const selected = plan?.routes.find((r) => r.id === selectedId) ?? null
  const others = useMemo(() => plan?.routes.filter((r) => r.id !== selectedId) ?? [], [plan, selectedId])

  const checkpointPoints = useMemo<GeoJSON.FeatureCollection<GeoJSON.Point>>(
    () => ({
      type: 'FeatureCollection',
      features: (selected?.checkpoints ?? []).map((cp, index) => ({
        type: 'Feature',
        properties: { index, level: cp.level ?? -1 },
        geometry: { type: 'Point', coordinates: [cp.lon, cp.lat] },
      })),
    }),
    [selected],
  )

  // The slider only swaps this rule: no new data, no request (#53).
  const heatColor = useMemo(() => levelColorExpression(`h${hour}`) as ExpressionSpecification, [hour])

  // Fit the map to a new plan.
  useEffect(() => {
    if (!plan || plan.routes.length === 0) return
    const [west, south, east, north] = bounds(plan.routes)
    map.current?.fitBounds(
      [
        [west, south],
        [east, north],
      ],
      { padding: 60, duration: 800 },
    )
  }, [plan])

  // Before a plan, show the chosen places.
  useEffect(() => {
    if (plan) return
    const place = destination ?? origin
    if (place) map.current?.flyTo({ center: [place.lon, place.lat], zoom: 6, duration: 800 })
  }, [origin, destination, plan])

  function onClick(event: MapLayerMouseEvent) {
    const feature = event.features?.[0]
    if (!feature) {
      props.onOpenCheckpoint(null)
      return
    }
    if (feature.layer.id === 'checkpoints') {
      props.onOpenCheckpoint(Number(feature.properties.index))
    } else if (feature.layer.id.startsWith('route-line-')) {
      props.onSelectRoute(feature.layer.id.slice('route-line-'.length) as RouteResult['id'])
    }
  }

  const popup = selected && openCheckpoint !== null ? selected.checkpoints[openCheckpoint] : null

  return (
    <Map
      ref={map}
      initialViewState={START_VIEW}
      mapStyle={STYLE}
      style={{ width: '100%', height: '100%' }}
      attributionControl={{ compact: true }}
      interactiveLayerIds={['checkpoints', ...(plan?.routes.map((r) => `route-line-${r.id}`) ?? [])]}
      onClick={onClick}
      onMoveEnd={(event) => {
        const center = event.target.getCenter()
        props.onCenter({ lat: center.lat, lon: center.lng })
      }}
      cursor="auto"
    >
      <NavigationControl position="top-right" showCompass={false} />

      {plan?.heatmap && (
        <Source id="heatmap" type="geojson" data={plan.heatmap.cells}>
          <Layer
            id="heatmap-squares"
            type="fill"
            paint={{ 'fill-color': heatColor, 'fill-opacity': 0.35, 'fill-outline-color': 'rgba(255,255,255,0.4)' }}
          />
        </Source>
      )}

      {others.map((route) => (
        <Source key={route.id} id={`route-${route.id}`} type="geojson" data={route.segments}>
          <Layer
            id={`route-line-${route.id}`}
            type="line"
            layout={{ 'line-cap': 'round', 'line-join': 'round' }}
            paint={{ 'line-color': '#64748b', 'line-width': 4, 'line-opacity': 0.55 }}
          />
        </Source>
      ))}

      {selected && (
        <Source key={selected.id} id={`route-${selected.id}`} type="geojson" data={selected.segments}>
          <Layer
            id={`route-casing-${selected.id}`}
            type="line"
            layout={{ 'line-cap': 'round', 'line-join': 'round' }}
            paint={{ 'line-color': '#ffffff', 'line-width': 9 }}
          />
          <Layer
            id={`route-line-${selected.id}`}
            type="line"
            layout={{ 'line-cap': 'round', 'line-join': 'round' }}
            paint={{ 'line-color': levelColorExpression('level') as ExpressionSpecification, 'line-width': 6 }}
          />
        </Source>
      )}

      {selected && (
        <Source id="checkpoints" type="geojson" data={checkpointPoints}>
          <Layer
            id="checkpoints"
            type="circle"
            paint={{
              'circle-radius': 5,
              'circle-color': levelColorExpression('level') as ExpressionSpecification,
              'circle-stroke-color': '#1f2937',
              'circle-stroke-width': 1.5,
            }}
          />
          <Layer
            id="checkpoints-risky"
            type="circle"
            filter={['>=', ['get', 'level'], 3] as FilterSpecification}
            paint={{ 'circle-radius': 9, 'circle-color': 'transparent', 'circle-stroke-color': '#d93025', 'circle-stroke-width': 2 }}
          />
        </Source>
      )}

      {origin && <Marker longitude={origin.lon} latitude={origin.lat} color="#1f2937" />}
      {destination && <Marker longitude={destination.lon} latitude={destination.lat} color="#475569" />}

      {popup && plan && (
        <Popup
          longitude={popup.lon}
          latitude={popup.lat}
          anchor="bottom"
          offset={12}
          onClose={() => props.onOpenCheckpoint(null)}
          closeOnClick={false}
          maxWidth="280px"
        >
          <CheckpointPopup checkpoint={popup} timezone={plan.timezone} />
        </Popup>
      )}
    </Map>
  )
}

function CheckpointPopup({ checkpoint: cp, timezone }: { checkpoint: Checkpoint; timezone: string }) {
  const why = cp.drivers.length > 0 ? ` from ${cp.drivers.join(' and ')}` : ''
  return (
    <div className="popup">
      <p className="popup-head">
        Mile {Math.round(cp.mile)} · {formatClock(cp.eta, timezone)} {zoneAbbreviation(cp.eta, timezone)}
      </p>
      <p>
        <span className="swatch" style={{ background: levelColor(cp.level) }} />
        <strong>{cp.label}</strong>
        {why}
      </p>
      {cp.load_escalated && (
        <p className="popup-note">Raised from {cp.wind_before_load} by your load.</p>
      )}
      {cp.weather && (
        <dl>
          <dt>Wind</dt>
          <dd>
            {cp.weather.wind_mph} mph (gusts {cp.weather.gust_mph})
          </dd>
          <dt>Rain</dt>
          <dd>{cp.weather.rain_in_hr} in/hr</dd>
          <dt>Snow</dt>
          <dd>{cp.weather.snow_in_hr} in/hr</dd>
        </dl>
      )}
    </div>
  )
}
