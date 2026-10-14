export function marketViewState({ loading, error, items }) {
  if (loading) return 'loading';
  if (error) return 'error';
  return items?.length ? 'ready' : 'empty';
}
