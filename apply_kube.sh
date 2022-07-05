kubectl create secret generic influxdb-creds \
  --from-literal=INFLUXDB_USERNAME=root \
  --from-literal=INFLUXDB_PASSWORD=root \
  --from-literal=INFLUXDB_HOST=influxdb

kubectl create configmap grafana-config \
  --from-file=dashboard.yaml=docker/grafana/dashboard.yaml \
  --from-file=datasource.yaml=docker/grafana/datasource.yaml \
  --from-file=DashboardTelegraf.json=docker/grafana/DashboardTelegraf.json

kubectl create configmap influxdb-config \
  --from-file=influxdb.conf=docker/influxdb/influxdb.conf

kubectl expose deployment grafana --port=3000 --target-port=3000 --protocol=TCP --type=NodePort
kubectl expose deployment influxdb --port=8086 --target-port=8086 --protocol=TCP --type=NodePort