#!/usr/bin/env python3
"""Converte o disco qcow2 gerado pelo Packer/QEMU em DevOps-Lab.ova
pronto para o Oracle VirtualBox (Arquivo > Importar Appliance).

Uso: python3 ci/make-ova.py output-qemu/DevOps-Lab.qcow2 output/DevOps-Lab.ova
"""
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import uuid

NAME = "DevOps-Lab"
CPUS = 2
MEMORY_MB = 4096
VRAM_MB = 128


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(qcow2, ova):
    out_dir = os.path.dirname(os.path.abspath(ova))
    os.makedirs(out_dir, exist_ok=True)
    vmdk_name = f"{NAME}-disk001.vmdk"
    ovf_name = f"{NAME}.ovf"
    mf_name = f"{NAME}.mf"
    vmdk = os.path.join(out_dir, vmdk_name)
    ovf = os.path.join(out_dir, ovf_name)
    mf = os.path.join(out_dir, mf_name)

    info = json.loads(subprocess.check_output(
        ["qemu-img", "info", "--output=json", qcow2]))
    capacity = int(info["virtual-size"])

    subprocess.check_call([
        "qemu-img", "convert", "-p", "-O", "vmdk",
        "-o", "subformat=streamOptimized,adapter_type=lsilogic",
        qcow2, vmdk])
    vmdk_size = os.path.getsize(vmdk)

    disk_uuid = str(uuid.uuid4())

    ovf_xml = f"""<?xml version="1.0"?>
<Envelope ovf:version="1.0" xml:lang="en-US"
  xmlns="http://schemas.dmtf.org/ovf/envelope/1"
  xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1"
  xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData"
  xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:vbox="http://www.virtualbox.org/ovf/machine">
  <References>
    <File ovf:id="file1" ovf:href="{vmdk_name}" ovf:size="{vmdk_size}"/>
  </References>
  <DiskSection>
    <Info>List of the virtual disks used in the package</Info>
    <Disk ovf:capacity="{capacity}" ovf:diskId="vmdisk1" ovf:fileRef="file1"
      ovf:format="http://www.vmware.com/interfaces/specifications/vmdk.html#streamOptimized"
      vbox:uuid="{disk_uuid}"/>
  </DiskSection>
  <NetworkSection>
    <Info>Logical networks used in the package</Info>
    <Network ovf:name="NAT">
      <Description>Logical network used by this appliance.</Description>
    </Network>
  </NetworkSection>
  <VirtualSystem ovf:id="{NAME}">
    <Info>A virtual machine</Info>
    <ProductSection>
      <Info>Meta-information about the installed software</Info>
      <Product>DevOps Lab</Product>
      <Version>1.0</Version>
    </ProductSection>
    <AnnotationSection>
      <Info>A human-readable annotation</Info>
      <Annotation>Ubuntu 24.04 LTS + XFCE com VS Code, Docker, Docker Compose, Git, Ansible, Terraform, Python e Jenkins. Usuario: aluno / Senha: devops</Annotation>
    </AnnotationSection>
    <OperatingSystemSection ovf:id="94">
      <Info>The kind of installed guest operating system</Info>
      <Description>Ubuntu_64</Description>
      <vbox:OSType ovf:required="false">Ubuntu_64</vbox:OSType>
    </OperatingSystemSection>
    <VirtualHardwareSection>
      <Info>Virtual hardware requirements for a virtual machine</Info>
      <System>
        <vssd:ElementName>Virtual Hardware Family</vssd:ElementName>
        <vssd:InstanceID>0</vssd:InstanceID>
        <vssd:VirtualSystemIdentifier>{NAME}</vssd:VirtualSystemIdentifier>
        <vssd:VirtualSystemType>virtualbox-2.2</vssd:VirtualSystemType>
      </System>
      <Item>
        <rasd:Caption>{CPUS} virtual CPU</rasd:Caption>
        <rasd:Description>Number of virtual CPUs</rasd:Description>
        <rasd:ElementName>{CPUS} virtual CPU</rasd:ElementName>
        <rasd:InstanceID>1</rasd:InstanceID>
        <rasd:ResourceType>3</rasd:ResourceType>
        <rasd:VirtualQuantity>{CPUS}</rasd:VirtualQuantity>
      </Item>
      <Item>
        <rasd:AllocationUnits>MegaBytes</rasd:AllocationUnits>
        <rasd:Caption>{MEMORY_MB} MB of memory</rasd:Caption>
        <rasd:Description>Memory Size</rasd:Description>
        <rasd:ElementName>{MEMORY_MB} MB of memory</rasd:ElementName>
        <rasd:InstanceID>2</rasd:InstanceID>
        <rasd:ResourceType>4</rasd:ResourceType>
        <rasd:VirtualQuantity>{MEMORY_MB}</rasd:VirtualQuantity>
      </Item>
      <Item>
        <rasd:Address>0</rasd:Address>
        <rasd:Caption>sataController0</rasd:Caption>
        <rasd:Description>SATA Controller</rasd:Description>
        <rasd:ElementName>sataController0</rasd:ElementName>
        <rasd:InstanceID>3</rasd:InstanceID>
        <rasd:ResourceSubType>AHCI</rasd:ResourceSubType>
        <rasd:ResourceType>20</rasd:ResourceType>
      </Item>
      <Item>
        <rasd:AddressOnParent>0</rasd:AddressOnParent>
        <rasd:Caption>disk1</rasd:Caption>
        <rasd:Description>Disk Image</rasd:Description>
        <rasd:ElementName>disk1</rasd:ElementName>
        <rasd:HostResource>/disk/vmdisk1</rasd:HostResource>
        <rasd:InstanceID>4</rasd:InstanceID>
        <rasd:Parent>3</rasd:Parent>
        <rasd:ResourceType>17</rasd:ResourceType>
      </Item>
      <Item>
        <rasd:AutomaticAllocation>true</rasd:AutomaticAllocation>
        <rasd:Caption>Ethernet adapter on 'NAT'</rasd:Caption>
        <rasd:Connection>NAT</rasd:Connection>
        <rasd:ElementName>Ethernet adapter on 'NAT'</rasd:ElementName>
        <rasd:InstanceID>5</rasd:InstanceID>
        <rasd:ResourceSubType>E1000</rasd:ResourceSubType>
        <rasd:ResourceType>10</rasd:ResourceType>
      </Item>
    </VirtualHardwareSection>
  </VirtualSystem>
</Envelope>
"""
    with open(ovf, "w", encoding="utf-8") as f:
        f.write(ovf_xml)

    with open(mf, "w", encoding="ascii") as f:
        f.write(f"SHA256({ovf_name})= {sha256(ovf)}\n")
        f.write(f"SHA256({vmdk_name})= {sha256(vmdk)}\n")

    # OVA = tar (formato ustar) com o .ovf primeiro
    with tarfile.open(ova, "w", format=tarfile.USTAR_FORMAT) as tar:
        for path, arc in ((ovf, ovf_name), (vmdk, vmdk_name), (mf, mf_name)):
            ti = tar.gettarinfo(path, arcname=arc)
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = "someone"
            ti.mode = 0o644
            with open(path, "rb") as fh:
                tar.addfile(ti, fh)
    for p in (ovf, vmdk, mf):
        os.remove(p)

    size_gb = os.path.getsize(ova) / (1024 ** 3)
    print(f"OVA gerado: {ova} ({size_gb:.2f} GB)")
    if size_gb > 3.8:
        print("::warning::O .ova passou do limite de 3,8 GB", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
