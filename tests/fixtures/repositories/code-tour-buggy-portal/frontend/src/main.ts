const islandRegistry = {
  dashboard: () => import('./islands/dashboard'),
  reports: () => import('./islands/reports'),
}

export default islandRegistry
