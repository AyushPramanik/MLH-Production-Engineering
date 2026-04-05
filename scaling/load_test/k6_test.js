import http from 'k6/http';
import { sleep } from 'k6';

export let options = {
  vus: 50,
  duration: '30s',
};

export default function () {
  http.get('http://localhost:5001/health');
  sleep(1);
}