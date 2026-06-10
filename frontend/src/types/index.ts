/**
 * Shared TypeScript types for the application.
 *
 * These types are used across islands and components. Feature-specific types
 * should live close to the feature that owns them so the shared surface stays
 * small and generic.
 */

/**
 * Props passed to islands via the `data-props` attribute.
 *
 * Each island receives its initial data from the server. Most islands in this
 * app fetch richer JSON state after hydration, but the type stays generic for
 * cases where templates do provide initial props.
 */
export type IslandProps<T = unknown> = {
  initialData?: T
}
