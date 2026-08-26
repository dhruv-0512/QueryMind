import { useState, useEffect } from 'react';
import { getApiActivityState, subscribeApiActivity } from '../services/api';

export const useApiStatus = () => {
  const [activity, setActivity] = useState(() => getApiActivityState());

  useEffect(() => {
    const unsubscribe = subscribeApiActivity((newState) => {
      setActivity(newState);
    });
    return unsubscribe;
  }, []);

  return activity;
};
