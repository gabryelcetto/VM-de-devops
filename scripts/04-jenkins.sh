#!/usr/bin/env bash
# 04 - Jenkins LTS (requer Java 21)
set -euxo pipefail

APT="apt-get -y -o DPkg::Lock::Timeout=900 -o APT::Install-Recommends=false -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"

$APT install fontconfig openjdk-21-jre-headless

curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2026.key \
  -o /etc/apt/keyrings/jenkins-keyring.asc
chmod a+r /etc/apt/keyrings/jenkins-keyring.asc
echo "deb [signed-by=/etc/apt/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian-stable binary/" \
  > /etc/apt/sources.list.d/jenkins.list

$APT update
$APT install jenkins

# Jenkins pode usar o Docker nos pipelines
usermod -aG docker jenkins
systemctl enable jenkins
systemctl restart jenkins

# Espera a senha inicial do assistente de configuração ser gerada (até 5 min)
for _ in $(seq 1 60); do
  [ -s /var/lib/jenkins/secrets/initialAdminPassword ] && break
  sleep 5
done
test -s /var/lib/jenkins/secrets/initialAdminPassword
