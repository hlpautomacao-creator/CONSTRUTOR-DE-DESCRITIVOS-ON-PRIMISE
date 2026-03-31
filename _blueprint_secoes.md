# Blueprint de Seções — Construtor de Descritivo Funcional
**Toledo do Brasil | Guardian PRO**
_Atualizado em: 2026-03-30_

---

## Regra geral

- **Seções fixas** → aparecem em TODOS os descritivos, independentemente de operação ou módulo
- **Seções condicionais** → aparecem apenas quando determinada operação ou módulo está ativo em pelo menos um PC
- **Ordem das seções condicionais** → segue a **ordem dos PCs** conforme configurado pelo analista no builder

---

## Seções Fixas (sempre presentes)

| # | Seção | Observações |
|---|-------|-------------|
| 1 | **Capa** | Logo Guardian, logo cliente (~5cm após tabela CT/OV), nome cliente, unidade, versão, data |
| 2 | **Informações do Documento** | Tabela de metadados do projeto |
| 3 | **Histórico de Revisões** | Tabela de revisões |
| 4 | **Índice** | Sumário automático |
| 5 | **Sobre o Cliente** | Texto institucional + **imagem da unidade do cliente** (logo cliente posicionada aqui, não na capa) |
| 6 | **Responsáveis** | Tabela com responsáveis Toledo e cliente |
| 7 | **Composição da Solução** | Módulos adquiridos, infraestrutura |
| 8 | **Objetivo da Solução** | Descrição do objetivo do Guardian |
| 9 | **Objetivo do Descritivo Funcional** | Explicação do documento |
| 10 | **Fluxos** | Diagrama(s) de fluxo do processo |
| 11 | **Estrutura do Guardian** | Hierarquia / arquitetura do sistema |
| 12 | **Conceitos do Guardian** | Glossário de termos do sistema |
| 13 | **Licenciamento Prix Cloud** | Tabela de licenças |
| 14 | **Documentação do Guardian** | Links / referências de documentação |
| 15 | **Responsabilidades do Cliente** | O que é de responsabilidade do cliente |
| 16 | **Aprovação** | Assinaturas / aprovação do documento |

---

## Seções Condicionais (por operação/módulo, na ordem dos PCs)

### Integração ERP
| Condição | Seção |
|----------|-------|
| Módulo ERP ativo + tipo WebService | **Integração ERP — WebService** |
| Módulo ERP ativo + tipo Arquivo Texto | **Integração ERP — Arquivo Texto** |
| Módulo ERP ativo + tipo Banco Tanque | **Integração ERP — Banco Tanque** |

### Monitor de Integração
| Condição | Seção |
|----------|-------|
| Módulo Monitor de Integração ativo | **Monitor de Integração** |

### Operações por PC (seguem ordem dos PCs)
Para cada PC configurado, as operações abaixo aparecem conforme marcadas:

| Operação no PC | Seção gerada |
|----------------|-------------|
| Pré-Cadastro | **Pré-Cadastro** |
| Cadastramento | **Cadastramento** |
| Portaria Entrada | **Portaria Entrada** |
| Pesagem | **Pesagem** |
| Inspeção | **Inspeção de Qualidade** |
| Tulha | **Tulha** |
| Moega | **Moega** |
| Portaria Saída | **Portaria Saída** |

> ⚠️ **Regra de ordem**: As seções de operação devem aparecer respeitando a sequência dos PCs:
> Todas as operações do PC1 primeiro, depois PC2, etc.

### Módulos Complementares
| Condição | Seção |
|----------|-------|
| Módulo Filas ativo | **Filas** |
| Módulo YMS ativo | **YMS (Yard Management System)** |
| Módulo Agendamento ativo | **Agendamento** |
| Módulo Guardian Fácil ativo | **Guardian Fácil** |
| Módulo Gestor Web ativo | **Gestor Web** |
| Módulo Cloud Prix ativo | **Cloud Prix** |
| Campos Adicionais configurados | **Campos Adicionais** |
| Relatórios configurados | **Relatórios** |
| Integração AD ativa | **Active Directory (AD)** |
| Módulo Filas (conceito) | **Conceito de Filas** |

---

## Notas de implementação

### Imagem da unidade do cliente (`clientImgB64`)
- **Onde aparece**: Seção "Sobre o Cliente" (após o primeiro H1 do campo `htmlContent`)
- **NÃO aparece**: Na capa (foi movida)
- **Tamanho**: Largura máxima 14cm, altura calculada pelo ratio real da imagem

### Imagem do logo do cliente (`clientLogob64`)
- **Onde aparece**: Capa — após a tabela CT/OV, ~5cm de altura
- **Ratio**: Calculado automaticamente via `getImageAspectRatio()`

### Logo Guardian (banner)
- **Onde aparece**: Topo da capa
- **Ratio fixo**: 0.418 (altura/largura)
- **Largura**: 17.8cm

---

## Histórico deste blueprint
| Data | Alteração |
|------|-----------|
| 2026-03-30 | Criação inicial — estrutura validada com análise de 5 modelos de referência |
