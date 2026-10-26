# Custom - Hosts Report

This Satellite report template produces a CSV inventory of all registered hosts, including hardware profile, operating system, registration time, taxonomy, and content source (capsule).

## Columns

| Column | Description |
|--------|-------------|
| Name | Host FQDN |
| Type | `physical` or `virtual` (from host reported data) |
| Sockets | CPU socket count |
| Cores | CPU core count |
| OS | Operating system name (for example `RedHat`, `OracleLinux`) |
| OS Version | Major.minor version (for example `9.8`) |
| Hypervisor | Hypervisor host name when Satellite knows the guest-to-host mapping |
| Registered Date/Time | Subscription Manager registration timestamp (UTC) |
| Organization | Host organization |
| Location | Host location |
| Capsule | Content source Smart Proxy (capsule) assigned to the host |

### Notes

- **Hypervisor** is blank unless Satellite has guest-to-hypervisor associations (typically via virt-who). Guests may still show as `virtual` from facts without a hypervisor name.
- **Registered Date/Time** can be blank for hosts that were never registered through Subscription Manager (for example the Satellite server itself in some setups).
- **Capsule** reflects the host content source; it may be blank if none is assigned.
- Socket and core values come from Satellite reported data / facts. Accuracy depends on hosts checking in with up-to-date facts.

---

## Enable the report in Satellite

You can enable this report with **Hammer** or in the **Satellite web UI**. Both methods create the same `Custom - Hosts` report template. Use either path below after preparing the template content.

### 1. Prepare the template content

Create `hosts_report_template.erb` with the following content (required for Hammer; for the UI you can paste this same ERB into the editor):

```erb
<%- report_headers 'Name', 'Type', 'Sockets', 'Cores', 'OS', 'OS Version', 'Hypervisor', 'Registered Date/Time', 'Organization', 'Location', 'Capsule' -%>
<%- load_hosts(includes: [:operatingsystem, :reported_data, :organization, :location], preload: [:subscription_facet, :content_facet]).each_record do |host| -%>
<%-   os_name = '' -%>
<%-   os_version = '' -%>
<%-   if host.operatingsystem -%>
<%-     os_name = host.operatingsystem.name -%>
<%-     os_major = host.operatingsystem.major.to_s -%>
<%-     os_minor = host.operatingsystem.minor.to_s -%>
<%-     if os_minor.empty? -%>
<%-       os_version = os_major -%>
<%-     else -%>
<%-       os_version = os_major + '.' + os_minor -%>
<%-     end -%>
<%-   end -%>
<%-   virt_host = '' -%>
<%-   if host.hypervisor_host -%>
<%-     virt_host = host.hypervisor_host.name -%>
<%-   end -%>
<%-   org_name = '' -%>
<%-   if host.organization -%>
<%-     org_name = host.organization.name -%>
<%-   end -%>
<%-   loc_name = '' -%>
<%-   if host.location -%>
<%-     loc_name = host.location.name -%>
<%-   end -%>
<%-   capsule_name = '' -%>
<%-   if host.content_source -%>
<%-     capsule_name = host.content_source.name -%>
<%-   end -%>
<%-   report_row(
      'Name': host.name,
      'Type': (host.virtual ? 'virtual' : 'physical'),
      'Sockets': host.sockets,
      'Cores': host.cores,
      'OS': os_name,
      'OS Version': os_version,
      'Hypervisor': virt_host,
      'Registered Date/Time': registered_at(host),
      'Organization': org_name,
      'Location': loc_name,
      'Capsule': capsule_name
    ) -%>
<%- end -%>
<%= report_render -%>
```

### 2a. Enable with Hammer

Replace `YourOrg` and `YourLocation` with values that exist in your Satellite:

```bash
hammer report-template create \
  --name "Custom - Hosts" \
  --file ./hosts_report_template.erb \
  --organizations "YourOrg" \
  --locations "YourLocation"
```

To update the ERB on an existing template:

```bash
hammer report-template update \
  --name "Custom - Hosts" \
  --file ./hosts_report_template.erb
```

Confirm it was created:

```bash
hammer report-template list --search 'name = "Custom - Hosts"'
```

### 2b. Enable in the Satellite UI

1. In the Satellite web UI, navigate to **Monitor → Report Templates**.
2. Click **Create Report Template**.
3. Set the name to `Custom - Hosts`.
4. Paste the ERB content from step 1 into the template editor.
5. Under **Organizations** and **Locations**, assign the taxonomies that should be able to use the report.
6. Click **Submit**.

To change the template later in the UI: open **Custom - Hosts** → **Edit**, update the ERB and taxonomies, then submit.

---

## Generate the report

You can generate the CSV with **Hammer** or from the **Satellite web UI**.

### Generate with Hammer

```bash
hammer report-template generate \
  --name "Custom - Hosts" \
  --report-format csv \
  --path /path/to/output/dir
```

Hammer writes a file such as:

```text
/path/to/output/dir/Custom - Hosts-YYYY-MM-DD.csv
```

Useful options:

| Option | Purpose |
|--------|---------|
| `--report-format csv` | CSV output (default for this use case) |
| `--report-format json` | JSON instead of CSV |
| `--path DIR` | Directory where the generated file is saved |
| `--organization "YourOrg"` | Scope generation to an organization context |
| `--location "YourLocation"` | Scope generation to a location context |

Verify the template exists before generating:

```bash
hammer report-template list --search 'name = "Custom - Hosts"'
hammer report-template dump --name "Custom - Hosts"
```

### Generate in the Satellite UI

1. In the Satellite web UI, navigate to **Monitor → Report Templates**.
2. Locate **Custom - Hosts** in the list (use the search box if needed).
3. Click the **Custom - Hosts** template name to open it, or use the row action menu and choose **Generate**.
4. On the generate screen, set **Output format** to **CSV** (JSON, YAML, or HTML are also available if needed).
5. Ensure the correct **Organization** and **Location** context is selected in the UI masthead if your Satellite uses taxonomy switching.
6. Click **Generate**.
7. When generation completes, download the resulting file from the browser.
---

## Example output

```csv
Name,Type,Sockets,Cores,OS,OS Version,Hypervisor,Registered Date/Time,Organization,Location,Capsule
a3matx.bk.lab,physical,1,8,RedHat,9.8,"",2025-10-01 13:38:56 UTC,HomeLab,GWT89,satellite.bk.lab
idm01.bk.lab,virtual,2,1,RedHat,10.2,"",2026-05-26 15:19:02 UTC,HomeLab,GWT89,satellite.bk.lab
```
