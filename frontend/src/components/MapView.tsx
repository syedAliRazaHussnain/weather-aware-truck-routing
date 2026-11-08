// The map: heatmap squares, routes coloured by risk, checkpoint dots and popups.
// Everything is drawn as MapLibre layers (not React elements), and the heatmap
// slider only changes one colour rule, so panning and sliding stay smooth (#53).
import { type ExpressionSpecification, type FilterSpecification, setWorkerUrl } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useMemo, useRef, useState } from 'react'
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
import { MAP_STYLE, START_VIEW } from '../lib/map'
import { levelColor, levelColorExpression } from '../lib/risk'
import { bounds } from '../lib/routes'
import { formatClock, zoneAbbreviation } from '../lib/time'

// MapLibre 6 finds its web worker next to its own file, which bundlers move; point
// it at the worker explicitly so it loads in development and in the built app.
setWorkerUrl(workerUrl)


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
  const [hovering, setHovering] = useState(false)

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
      // Extra room at the bottom for the slider and legend over the map.
      { padding: { top: 50, left: 50, right: 50, bottom: 170 }, duration: 800 },
    )
  }, [plan])

  // Before a plan, show the chosen places: both of them once both are picked.
  useEffect(() => {
    if (plan) return
    if (origin && destination) {
      map.current?.fitBounds(
        [
          [Math.min(origin.lon, destination.lon), Math.min(origin.lat, destination.lat)],
          [Math.max(origin.lon, destination.lon), Math.max(origin.lat, destination.lat)],
        ],
        { padding: 80, duration: 800, maxZoom: 9 },
      )
      return
    }
    const place = destination ?? origin
    if (place) map.current?.flyTo({ center: [place.lon, place.lat], zoom: 6, duration: 800 })
  }, [origin, destination, plan])

  function onClick(event: MapLayerMouseEvent) {
    const features = event.features ?? []
    // A checkpoint wins over the route line under it, so dots are easy to click.
    const checkpoint = features.find((f) => f.layer.id === 'checkpoints-hit')
    const line = features.find((f) => /^route-(line|hit)-/.test(f.layer.id))
    if (checkpoint) {
      props.onOpenCheckpoint(Number(checkpoint.properties.index))
    } else if (line) {
      props.onSelectRoute(line.layer.id.slice(-1) as RouteResult['id'])
    } else {
      props.onOpenCheckpoint(null)
    }
  }

  const popup = selected && openCheckpoint !== null ? selected.checkpoints[openCheckpoint] : null

  return (
    <Map
      ref={map}
      initialViewState={START_VIEW}
      mapStyle={MAP_STYLE}
      style={{ width: '100%', height: '100%' }}
      attributionControl={{ compact: true }}
      interactiveLayerIds={[
        'checkpoints-hit',
        ...(plan?.routes.flatMap((r) => [`route-line-${r.id}`, `route-hit-${r.id}`]) ?? []),
      ]}
      onClick={onClick}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      onMoveEnd={(event) => {
        const center = event.target.getCenter()
        props.onCenter({ lat: center.lat, lon: center.lng })
      }}
      cursor={hovering ? 'pointer' : 'grab'}
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
          {/* A wide invisible line, so a thin faded route is easy to click. */}
          <Layer
            id={`route-hit-${route.id}`}
            type="line"
            paint={{ 'line-color': '#000', 'line-width': 16, 'line-opacity': 0 }}
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
            id="checkpoints-hit"
            type="circle"
            paint={{ 'circle-radius': 12, 'circle-color': '#000', 'circle-opacity': 0 }}
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
