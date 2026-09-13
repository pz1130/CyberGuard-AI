import { createContext, useContext } from 'react'
import type { Tab } from '../components/SidebarNew'

export interface SearchTarget {
  tab: Tab
  id: number | string
  name: string
  subview?: string
}

interface SearchContextValue {
  searchTarget: SearchTarget | null
  setSearchTarget: (t: SearchTarget | null) => void
}

export const SearchContext = createContext<SearchContextValue>({
  searchTarget: null,
  setSearchTarget: () => {},
})

export function useSearch() {
  return useContext(SearchContext)
}
