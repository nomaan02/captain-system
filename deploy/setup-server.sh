#!/bin/bash
# ================================================================
# Captain System — VPS Base Setup
# Run as root on a fresh Ubuntu 24.04 Hetzner VPS.
#
# Usage:
#   ssh root@<VPS_IP> 'bash -s' < deploy/setup-server.sh
# ================================================================
set -euo pipefail

echo "=== Captain VPS Setup ==="

# 1. System updates
echo "→ Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get upgrade -y -qq

# 2. Timezone
echo "→ Setting timezone to America/New_York..."
timedatectl set-timezone America/New_York

# 3. Create deploy user
echo "→ Creating captain user..."
if ! id captain &>/dev/null; then
    useradd -m -s /bin/bash captain
fi
mkdir -p /home/captain/.ssh /home/captain/logs
cp /root/.ssh/authorized_keys /home/captain/.ssh/
chown -R captain:captain /home/captain/.ssh /home/captain/logs
chmod 700 /home/captain/.ssh
chmod 600 /home/captain/.ssh/authorized_keys

# 4. Install Docker Engine (official method)
echo "→ Installing Docker..."
apt-get install -y -qq ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 5. Add captain user to docker group
usermod -aG docker captain
systemctl enable docker
systemctl start docker

# 6. Firewall
echo "→ Configuring firewall..."
apt-get install -y -qq ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp     # SSH
ufw allow 443/tcp    # HTTPS (GUI)
ufw allow 80/tcp     # HTTP (redirect)
ufw --force enable

# 7. Automatic security updates
echo "→ Enabling unattended upgrades..."
apt-get install -y -qq unattended-upgrades
echo 'Unattended-Upgrade::Automatic-Reboot "false";' > /etc/apt/apt.conf.d/51captain-noreboot

# 8. Fail2ban for SSH
echo "→ Installing fail2ban..."
apt-get install -y -qq fail2ban
systemctl enable fail2ban
systemctl start fail2ban

# 9. Swap (4 GB safety net)
echo "→ Creating swap..."
if [ ! -f /swapfile ]; then
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# 10. Harden SSH
echo "→ Hardening SSH..."
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd

echo ""
echo "============================================"
echo "  Server setup complete."
echo "  Docker: $(docker --version)"
echo "  User:   captain (SSH key copied)"
echo "  FW:     22, 80, 443 open"
echo "  Swap:   4 GB"
echo "============================================"
echo "  Next: reboot, then deploy captain-system"
echo "  ssh captain@$(hostname -I | awk '{print $1}')"
echo "============================================"
