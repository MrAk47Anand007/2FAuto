Name: twofauto-server
Version: 0.1.0
Release: 1%{?dist}
Summary: 2FAuto private vault and browser server
License: LicenseRef-2FAuto-Unspecified
BuildArch: x86_64
Requires: systemd

%description
Local 2FAuto vault and web application. Network access is initially loopback-only.

%install
install -Dm755 %{_sourcedir}/twofauto-runtime %{buildroot}/usr/lib/2fauto/twofauto-runtime
install -Dm644 %{_sourcedir}/twofauto.service %{buildroot}/usr/lib/systemd/system/twofauto.service

%pre
getent passwd twofauto >/dev/null || useradd --system --home-dir /var/lib/2fauto --shell /sbin/nologin twofauto
exit 0

%post
install -d -m 0700 -o twofauto -g twofauto /var/lib/2fauto
runuser -u twofauto -- /usr/lib/2fauto/twofauto-runtime init --role server --data-dir /var/lib/2fauto --if-missing
systemctl daemon-reload
systemctl enable --now twofauto.service

%preun
if [ "$1" -eq 0 ]; then
    systemctl disable --now twofauto.service || true
else
    systemctl stop twofauto.service || true
fi

%postun
systemctl daemon-reload || true

%files
%attr(0755,root,root) /usr/lib/2fauto/twofauto-runtime
%attr(0644,root,root) /usr/lib/systemd/system/twofauto.service
