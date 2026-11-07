// The app shell. Later PRs add the trip form, the map and the results panel.
import { useEffect } from 'react'
import { wakeServer } from './api/client'

export default function App() {
  useEffect(wakeServer, []) // #58: wake the free server while the driver types

  return (
    <main className="app">
      <h1>Weather-Aware Truck Routing</h1>
      <p>Plan truck routes around wind, rain and snow.</p>
    </main>
  )
}
